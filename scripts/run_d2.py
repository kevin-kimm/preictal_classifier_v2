"""D2 experiments 1-4 and the alarm step (docs/evaluation_methods.md v1.2, Section 10).

For every test patient (outer fold), each candidate is compared on that fold's inner
validation patients only, averaged over the seeds, and kept if it raises the mean
inner AUROC. The test patient is scored once, with the setup chosen for its fold,
so no test result influences any choice (nested cross-validation).

Steps, in order:
    normalize   off / on         causal per-recording scaling (30 min, past data only)
    context     0, 2, 5, 10 min  mean and slope of each feature over the preceding minutes
    clock       off / on         time-of-day features (CHB-MIT and Siena only)
    tusz        off / on         TUSZ interictal windows (half of TUSZ patients) added to training
    alarm       smoothing x persistence grid; threshold = lowest with inner FAR <= 5 per 24 h;
                the combination with the highest mean inner sensitivity is kept
Step 5 (a neural network) runs separately once PyTorch is installed.

Usage, from the repo root with .venv active:
    python scripts/run_d2.py --seeds 0          quicker preview (roughly an hour)
    python scripts/run_d2.py                    all five seeds (a few hours; run overnight)

Outputs in results/d2/: d2_report.md, d2_metrics.csv, d2_selection_log.csv,
d2_false_alarm_sets.csv, d2_summary.json. Normalized features are cached in
data/processed/d2_cache/ (not in Git).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.config import load_config  # noqa: E402
from preictal.data.labels import INTERICTAL, PREICTAL, LabelRules  # noqa: E402
from preictal.data.loaders import DEFAULT_CORRECTIONS  # noqa: E402
from preictal.evaluation.lopo import Fold, full_split, make_folds, read_label_report  # noqa: E402
from preictal.evaluation.metrics import (  # noqa: E402
    AlarmResult, Sequence, bootstrap_ci, chance_p_value, choose_threshold_bisect, evaluate_all, window_metrics,
)
from preictal.features.build_features import feature_version  # noqa: E402
from preictal.features.transforms import (  # noqa: E402
    clock_features, context_features, rolling_normalize, timeline_has_clock,
)
from preictal.models.model import build_model, predict_proba  # noqa: E402
from preictal.models.train import TRAIN_CLASSES, load_windows, sample_weights  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

STEPS = ("normalize", "context", "clock", "tusz")
OPTIONS = {"normalize": (False, True), "context": (0, 2, 5, 10), "clock": (False, True), "tusz": (False, True)}
ALARM_GRID = [(s, p) for s in (1, 6, 12, 36) for p in (1, 3, 6)]
SELECTION_EVERY = 2      # selection fits use every 2nd window (10 s apart); final models use all
TUSZ_EVERY = 6           # TUSZ interictal windows 30 s apart (non-overlapping)


@dataclass(frozen=True)
class Config:
    normalize: bool = False
    context: int = 0
    clock: bool = False
    tusz: bool = False

    def features_key(self):
        return (self.normalize, self.context, self.clock)

    def label(self):
        return (f"norm={'on' if self.normalize else 'off'} ctx={self.context}min "
                f"clock={'on' if self.clock else 'off'} tusz={'on' if self.tusz else 'off'}")


# ---------------------------------------------------------------- feature sets

class FeatureSet:
    """Pooled features for one group of windows, with cached D2 transforms."""

    def __init__(self, W, name, cache_dir, version, clock_ok):
        self.W, self.name = W, name
        self.clock = clock_features(W.t_end, clock_ok)
        cache = cache_dir / f"{name}_norm_{version}.npy"
        if cache.exists():
            self.norm = np.load(cache)
        else:
            print(f"  normalizing {name} features (one-off, cached)...")
            self.norm = rolling_normalize(W.X, W.timeline, W.t_end)
            cache_dir.mkdir(parents=True, exist_ok=True)
            np.save(cache, self.norm)
        self._ctx = {}

    def context(self, normalize: bool, minutes: int):
        key = (normalize, minutes)
        if key not in self._ctx:
            if len(self._ctx) >= 2:
                self._ctx.pop(next(iter(self._ctx)))
            base = self.norm if normalize else self.W.X
            self._ctx[key] = context_features(base, self.W.timeline, self.W.t_end, minutes * 60)
        return self._ctx[key]

    def build(self, key):
        normalize, minutes, clock = key
        parts = [self.norm if normalize else self.W.X]
        if minutes:
            parts.append(self.context(normalize, minutes))
        if clock:
            parts.append(self.clock)
        return np.hstack(parts) if len(parts) > 1 else parts[0]


# ---------------------------------------------------------------- helpers

def git_commit() -> str:
    try:
        c = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True,
                           text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "src", "scripts", "configs"], cwd=REPO,
                               capture_output=True, text=True, check=True).stdout.strip()
        return c + (" (uncommitted code changes)" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def auroc(y, s):
    y = np.asarray(y, bool)
    return float(roc_auc_score(y, s)) if y.any() and (~y).any() else float("nan")


def per_patient_auroc(W, rows, scores):
    out = []
    for code in np.unique(W.subject[rows]):
        m = W.subject[rows] == code
        lab = W.y[rows][m]
        pi = np.isin(lab, (PREICTAL, INTERICTAL))
        out.append(auroc(lab[pi] == PREICTAL, scores[m][pi]))
    return float(np.nanmean(out)) if out else float("nan")


def sequences(W, rows, scores, tl_info):
    out = []
    order = np.lexsort((W.t_end[rows], W.timeline[rows]))
    rows, scores = rows[order], scores[order]
    tl = W.timeline[rows]
    for code in np.unique(tl):
        m = tl == code
        info = tl_info[W.timelines[code]]
        out.append(Sequence(info["subject"], W.t_end[rows][m], scores[m], W.y[rows][m],
                            np.array(info["onsets"], float), np.array(info["eligible_onsets"], float)))
    return out


def every_other(W, rows, k):
    return rows[np.round(W.t_end[rows] / 5.0).astype(np.int64) % k == 0] if k > 1 else rows


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, nargs="+", default=None)
    ap.add_argument("--steps", nargs="+", default=list(STEPS), choices=STEPS)
    ap.add_argument("--features", type=Path, default=REPO / "data" / "processed" / "features")
    ap.add_argument("--d1", type=Path, default=REPO / "results" / "d1")
    ap.add_argument("--out", type=Path, default=REPO / "results" / "d2")
    args = ap.parse_args()
    t_start = time.time()

    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    ev, al = cfg["evaluation"], cfg["alarm"]
    seeds = args.seeds if args.seeds is not None else ev["seeds"]
    step_s = cfg["windows"]["step_s"]
    far_target = ev["far_target_per_24h"]["d2"]
    base_alarm = dict(sph_s=rules.sph_s, horizon_s=rules.preictal_start_s, refractory_s=al["refractory_min"] * 60)
    corrections = DEFAULT_CORRECTIONS.read_text() if DEFAULT_CORRECTIONS.exists() else ""
    version = feature_version(cfg, corrections)
    cache_dir = args.features.parent / "d2_cache"
    args.out.mkdir(parents=True, exist_ok=True)
    datasets = tuple(cfg["training"]["datasets"])
    steps = [s for s in STEPS if s in args.steps]

    subjects = read_label_report(args.d1 / "label_report.csv")
    tl_info = json.loads((args.features / "timelines.json").read_text())

    print("Loading features...")
    W = load_windows(args.features, datasets, version=version, keep_per_channel=False)
    FW = FeatureSet(W, "train", cache_dir, version, np.array([timeline_has_clock(k) for k in W.timelines])[W.timeline])
    print(f"  CHB-MIT and Siena: {len(W.y):,} windows")

    # TUSZ: split patients in half (seed 0). Half A may be used for training; half B only for false-alarm tests.
    T = FT = None
    tusz_half_a, tusz_half_b = set(), set()
    if (args.features / "tusz").exists():
        T = load_windows(args.features, ("tusz",), version=version, keep_per_channel=False, labels=(INTERICTAL,))
        FT = FeatureSet(T, "tusz", cache_dir, version, np.zeros(len(T.y), bool))
        names = sorted(T.subjects)
        rng = np.random.default_rng(0)
        half = set(rng.choice(names, size=len(names) // 2, replace=False).tolist())
        tusz_half_a, tusz_half_b = half, set(names) - half
        print(f"  TUSZ interictal: {len(T.y):,} windows, {len(names)} patients "
              f"({len(tusz_half_a)} may be used for training, {len(tusz_half_b)} held out)")
    elif "tusz" in steps:
        steps.remove("tusz")
        print("  TUSZ features not found; skipping the TUSZ step")
    t_rows_a = every_other(T, T.rows(tusz_half_a), TUSZ_EVERY) if T is not None else np.array([], int)

    folds_by_seed = {s: make_folds(subjects, datasets, s, ev["inner_validation_fraction"],
                                   ev["inner_validation_min_patients"]) for s in seeds}
    n_folds = len(folds_by_seed[seeds[0]])
    fold_ids = list(range(n_folds)) + ["full"]
    full_by_seed = {s: full_split(subjects, datasets, s, ev["inner_validation_fraction"],
                                  ev["inner_validation_min_patients"]) for s in seeds}

    def fold_of(fid, seed) -> Fold:
        return full_by_seed[seed] if fid == "full" else folds_by_seed[seed][fid]

    def train_matrix(cfg_: Config, fold: Fold, XW, XT, every: int):
        r = every_other(W, W.rows(set(fold.train)), every)
        r = r[np.isin(W.y[r], TRAIN_CLASSES)]                  # excluded windows are never trained on
        X, y, subj = [XW[r]], [W.y[r]], [W.subject[r]]
        if cfg_.tusz and T is not None:
            X.append(XT[t_rows_a]); y.append(T.y[t_rows_a]); subj.append(T.subject[t_rows_a] + 10_000)
        return np.vstack(X), np.concatenate(y), np.concatenate(subj)

    def fit_model(cfg_, fold, seed, XW, XT, every):
        X, y, subj = train_matrix(cfg_, fold, XW, XT, every)
        model = build_model(seed)
        model.fit(X, y, sample_weight=sample_weights(y, subj))
        return model

    # ---------------------------------------------------------------- selection (nested, per fold)
    inner_score = {}
    state = {f: Config() for f in fold_ids}
    log_rows = []

    def evaluate(needed):
        groups = defaultdict(list)
        for fid, c in needed:
            groups[c.features_key()].append((fid, c))
        todo = sum(1 for fid, c in needed for s in seeds if (fid, s, c) not in inner_score)
        bar = tqdm(total=todo, desc="  fits", leave=False) if tqdm else None
        for key in sorted(groups):
            XW = FW.build(key)
            XT = FT.build(key) if FT is not None and any(c.tusz for _, c in groups[key]) else None
            for fid, c in groups[key]:
                for s in seeds:
                    if (fid, s, c) in inner_score:
                        continue
                    fold = fold_of(fid, s)
                    model = fit_model(c, fold, s, XW, XT, SELECTION_EVERY)
                    r_inner = W.rows(set(fold.inner))
                    inner_score[(fid, s, c)] = per_patient_auroc(W, r_inner, predict_proba(model, XW[r_inner])[:, 0])
                    if bar:
                        bar.update(1)
        if bar:
            bar.close()

    def score(fid, c):
        return float(np.nanmean([inner_score[(fid, s, c)] for s in seeds]))

    for step in steps:
        print(f"Step: {step}")
        needed = {(f, replace(state[f], **{step: o})) for f in fold_ids for o in OPTIONS[step]}
        evaluate(needed)
        for f in fold_ids:
            current = state[f]
            options = {o: score(f, replace(current, **{step: o})) for o in OPTIONS[step]}
            best = max(options, key=lambda o: (options[o], o == getattr(current, step)))
            if options[best] > options[getattr(current, step)]:
                state[f] = replace(current, **{step: best})
            log_rows.append({"fold": f, "test": "" if f == "full" else fold_of(f, seeds[0]).test, "step": step,
                             "inner_auroc_by_option": json.dumps({str(o): round(v, 4) for o, v in options.items()}),
                             "chosen": getattr(state[f], step)})

    # ---------------------------------------------------------------- final models, alarms, test scoring
    print("Final models and alarms...")
    final = {}                      # (fid, seed) -> dict
    groups = defaultdict(list)
    for f in fold_ids:
        groups[state[f].features_key()].append(f)
    for key in sorted(groups):
        XW = FW.build(key)
        XT = FT.build(key) if FT is not None and any(state[f].tusz for f in groups[key]) else None
        for f in groups[key]:
            for s in seeds:
                fold = fold_of(f, s)
                model = fit_model(state[f], fold, s, XW, XT, 1)
                r_inner = W.rows(set(fold.inner))
                entry = {"model": model if f == "full" else None,
                         "inner_seqs": sequences(W, r_inner, predict_proba(model, XW[r_inner])[:, 0], tl_info)}
                if f != "full":
                    r_test = W.rows({fold.test})
                    entry.update(r_test=r_test, proba=predict_proba(model, XW[r_test]))
                    if state[f].clock:
                        nc = replace(state[f], clock=False)
                        XW_nc = XW[:, :-2]                      # the clock features are the last two columns
                        XT_nc = XT[:, :-2] if (nc.tusz and XT is not None) else None
                        m2 = fit_model(nc, fold, s, XW_nc, XT_nc, 1)
                        entry["auroc_without_clock"] = window_metrics(
                            W.y[r_test], predict_proba(m2, XW_nc[r_test]))["auroc"]
                final[(f, s)] = entry

    alarm_choice = {}
    for f in fold_ids:
        best, best_sens = (1, 1), -1.0
        for sm, pe in ALARM_GRID:
            kw = dict(base_alarm, smoothing=sm, persistence=pe)
            sens = []
            for s in seeds:
                seqs = final[(f, s)]["inner_seqs"]
                thr, _ = choose_threshold_bisect(seqs, far_target, step_s, al["threshold_candidates"], **kw)
                sens.append(evaluate_all(seqs, thr, step_s, **kw).sensitivity)
            m = float(np.nanmean(sens))
            if m > best_sens:
                best, best_sens = (sm, pe), m
        alarm_choice[f] = best
        for s in seeds:
            kw = dict(base_alarm, smoothing=best[0], persistence=best[1])
            final[(f, s)]["threshold"] = choose_threshold_bisect(final[(f, s)]["inner_seqs"], far_target, step_s,
                                                                 al["threshold_candidates"], **kw)[0]
            final[(f, s)]["alarm_kw"] = kw

    # clock-only reference baseline and D1 per-patient AUROC
    d1 = defaultdict(list)
    d1_file = args.d1 / "lopo_metrics.csv"
    if d1_file.exists():
        for r in csv.DictReader(open(d1_file)):
            if int(r["seed"]) in seeds:
                d1[r["subject"]].append(float(r["auroc"]))

    metric_rows, per_seed = [], {}
    for s in seeds:
        pooled = AlarmResult()
        for f in range(n_folds):
            fold, e = fold_of(f, s), final[(f, s)]
            r_test, proba = e["r_test"], e["proba"]
            wm = window_metrics(W.y[r_test], proba)
            ar = evaluate_all(sequences(W, r_test, proba[:, 0], tl_info), e["threshold"], step_s, **e["alarm_kw"])
            pooled = pooled.add(ar)
            tr = W.rows(set(fold.train))
            tr = tr[np.isin(W.y[tr], (PREICTAL, INTERICTAL)) & ~np.isnan(FW.clock[tr, 0])]
            te = r_test[np.isin(W.y[r_test], (PREICTAL, INTERICTAL)) & ~np.isnan(FW.clock[r_test, 0])]
            clock_auc = float("nan")
            if len(tr) and len(te):
                lr = LogisticRegression().fit(FW.clock[tr], W.y[tr] == PREICTAL)
                clock_auc = auroc(W.y[te] == PREICTAL, lr.predict_proba(FW.clock[te])[:, 1])
            metric_rows.append({
                "seed": s, "subject": fold.test, "dataset": subjects[fold.test].dataset, "setup": state[f].label(),
                "alarm_smoothing": e["alarm_kw"]["smoothing"], "alarm_persistence": e["alarm_kw"]["persistence"],
                "auroc": wm["auroc"], "auroc_without_clock": e.get("auroc_without_clock", wm["auroc"]),
                "clock_only_auroc": clock_auc, "d1_auroc": float(np.mean(d1[fold.test])) if d1[fold.test] else float("nan"),
                "macro_f1": wm["macro_f1"], "threshold": e["threshold"], "events": ar.n_events,
                "predicted": ar.n_predicted, "false_alarms": ar.n_false, "far_per_24h": ar.far_per_24h,
                "sensitivity": ar.sensitivity, "time_in_warning": ar.time_in_warning,
                "median_warning_s": float(np.median(ar.warning_times)) if ar.warning_times else float("nan"),
            })
        chance, pval = chance_p_value(pooled.n_predicted, pooled.n_events, pooled.far_per_24h,
                                      rules.preictal_start_s - rules.sph_s)
        rows = [r for r in metric_rows if r["seed"] == s]
        per_seed[s] = {"mean_auroc": float(np.nanmean([r["auroc"] for r in rows])),
                       "mean_auroc_without_clock": float(np.nanmean([r["auroc_without_clock"] for r in rows])),
                       "mean_clock_only": float(np.nanmean([r["clock_only_auroc"] for r in rows])),
                       "sensitivity": pooled.sensitivity, "far_per_24h": pooled.far_per_24h,
                       "time_in_warning": pooled.time_in_warning, "events": pooled.n_events,
                       "predicted": pooled.n_predicted, "chance_probability": chance, "p_value": pval}

    # ---------------------------------------------------------------- false-alarm sets and dataset check
    fa_rows, dataset_check = [], None
    key = state["full"].features_key()
    sets = []
    if FT is not None:
        sets.append(("tusz (held-out half)", T, FT, T.rows(tusz_half_b)))
    if (args.features / "mental_arith").exists():
        M = load_windows(args.features, ("mental_arith",), version=version, keep_per_channel=False,
                         labels=(INTERICTAL,))
        FM = FeatureSet(M, "mental_arith", cache_dir, version, np.zeros(len(M.y), bool))
        sets.append(("mental_arith", M, FM, np.arange(len(M.y))))
    built = {name: FD.build(key) for name, _, FD, _ in sets}
    for s in seeds:
        e = final[("full", s)]
        kw = dict(base_alarm, smoothing=alarm_choice["full"][0], persistence=alarm_choice["full"][1])
        thr = choose_threshold_bisect(e["inner_seqs"], far_target, step_s, al["threshold_candidates"], **kw)[0]
        for name, D, FD, rows in sets:
            seqs = sequences(D, rows, predict_proba(e["model"], built[name][rows])[:, 0], tl_info)
            total = evaluate_all(seqs, thr, step_s, **kw)
            fa_rows.append({"seed": s, "set": name, "setup": state["full"].label(), "hours": round(total.far_hours, 2),
                            "false_alarms": total.n_false, "far_per_24h": total.far_per_24h})
    if FT is not None and "tusz" in steps:
        key = (state["full"].normalize, state["full"].context, False)
        XW, XT = FW.build(key), FT.build(key)
        rw = every_other(W, np.flatnonzero(W.y == INTERICTAL), TUSZ_EVERY)
        X = np.vstack([XW[rw], XT[t_rows_a]])
        y = np.concatenate([np.zeros(len(rw)), np.ones(len(t_rows_a))])
        g = np.concatenate([W.subject[rw], T.subject[t_rows_a] + 10_000])
        scores = np.zeros(len(y))
        for tr, te in GroupKFold(n_splits=2).split(X, y, g):
            scores[te] = build_model(0).fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
        dataset_check = auroc(y == 1, scores)

    # ---------------------------------------------------------------- summary, VT-15 and VT-17
    by_subject = defaultdict(list)
    for r in metric_rows:
        by_subject[r["subject"]].append(r)
    subj_d2 = {k: float(np.nanmean([r["auroc"] for r in v])) for k, v in by_subject.items()}
    subj_d1 = {k: float(np.nanmean(d1[k])) for k in by_subject if d1[k]}
    mean_d2 = float(np.mean([per_seed[s]["mean_auroc"] for s in seeds]))
    sd_d2 = float(np.std([per_seed[s]["mean_auroc"] for s in seeds]))
    mean_d1 = float(np.mean(list(subj_d1.values()))) if subj_d1 else float("nan")
    rel = (mean_d2 - mean_d1) / mean_d1 if subj_d1 else float("nan")
    common = [k for k in subj_d2 if k in subj_d1]
    try:
        wil_p = float(wilcoxon([subj_d2[k] for k in common], [subj_d1[k] for k in common]).pvalue)
    except ValueError:
        wil_p = float("nan")
    ci = bootstrap_ci(list(subj_d2.values()), ev["bootstrap_resamples"], 0)
    mean_sens = float(np.mean([per_seed[s]["sensitivity"] for s in seeds]))
    mean_far = float(np.mean([per_seed[s]["far_per_24h"] for s in seeds]))
    max_p = float(np.max([per_seed[s]["p_value"] for s in seeds]))
    vt15 = rel >= 0.15
    vt17 = mean_sens >= 0.8 and mean_far <= far_target and max_p < 0.05
    all_seeds = seeds == ev["seeds"]

    def write(name, rows):
        if rows:
            with open(args.out / name, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
                w.writeheader()
                w.writerows(rows)

    write("d2_metrics.csv", metric_rows)
    write("d2_selection_log.csv", log_rows)
    write("d2_false_alarm_sets.csv", fa_rows)
    (args.out / "d2_summary.json").write_text(json.dumps({
        "seeds": seeds, "steps": steps, "per_seed": per_seed, "mean_auroc": mean_d2, "sd": sd_d2, "ci95": ci,
        "d1_mean_auroc_same_seeds": mean_d1, "relative_improvement": rel, "wilcoxon_p": wil_p,
        "full_data_setup": state["full"].label(), "full_data_alarm": alarm_choice["full"],
        "dataset_identifiability_auroc": dataset_check, "feature_version": version,
        "runtime_min": (time.time() - t_start) / 60}, indent=2))

    setups = defaultdict(int)
    for f in range(n_folds):
        setups[state[f].label()] += 1
    pf = lambda ok: "PASS" if ok else "FAIL"  # noqa: E731
    lines = [
        "# D2: experiments 1-4 and alarm logic", "",
        f"Generated {datetime.now().isoformat(timespec='seconds')} · commit {git_commit()} · Python "
        f"{platform.python_version()} · seeds {seeds} · steps {steps} · feature version {version} · "
        f"{(time.time() - t_start) / 60:.0f} min", "",
        "Method: docs/evaluation_methods.md v1.2. Every choice was made per fold on inner validation patients; "
        "no test result was used.", "",
        "## Results", "",
        "| Test | Result |", "|---|---|",
        f"| VT-15 improvement over D1 | {pf(vt15)}: mean per-patient AUROC {mean_d2:.3f} ± {sd_d2:.3f} "
        f"(95% CI {ci[0]:.3f}–{ci[1]:.3f}) vs D1 {mean_d1:.3f} on the same seeds: {100 * rel:+.1f}% "
        f"(target +15%). Wilcoxon p = {wil_p:.3g}. Nice to have (≥ 0.75): {'met' if mean_d2 >= 0.75 else 'not met'} |",
        f"| VT-17 event-level performance | {pf(vt17)}: sensitivity {mean_sens:.2f} (target ≥ 0.80), "
        f"{mean_far:.2f} false alarms per 24 h (target ≤ {far_target}), largest p vs chance {max_p:.3g} |",
        f"| Reference: clock-only model | mean AUROC {np.mean([per_seed[s]['mean_clock_only'] for s in seeds]):.3f} |",
        f"| D2 without time-of-day features | mean AUROC "
        f"{np.mean([per_seed[s]['mean_auroc_without_clock'] for s in seeds]):.3f} |",
    ]
    if not all_seeds:
        lines.append(f"| Note | Only seeds {seeds} were run; the plan requires all five |")
    lines += ["", "## Setups chosen (per test patient fold)", "", "| Setup | Folds |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(setups.items(), key=lambda kv: -kv[1])]
    lines += ["", f"Setup chosen on all patients (used for the false-alarm sets): {state['full'].label()}, "
              f"alarm smoothing {alarm_choice['full'][0]}, persistence {alarm_choice['full'][1]}."]
    if dataset_check is not None:
        lines.append(f"Dataset check: a model can tell TUSZ from CHB-MIT/Siena interictal windows with AUROC "
                     f"{dataset_check:.3f} (0.5 = indistinguishable).")
    lines += ["", "## Per seed", "",
              "| Seed | AUROC | Without clock | Clock only | Sensitivity | FAR / 24 h | Time in warning | Chance prob. | p |",
              "|---|---|---|---|---|---|---|---|---|"]
    for s in seeds:
        m = per_seed[s]
        lines.append(f"| {s} | {m['mean_auroc']:.3f} | {m['mean_auroc_without_clock']:.3f} | {m['mean_clock_only']:.3f} "
                     f"| {m['predicted']}/{m['events']} ({m['sensitivity']:.2f}) | {m['far_per_24h']:.2f} "
                     f"| {m['time_in_warning']:.3f} | {m['chance_probability']:.3f} | {m['p_value']:.3g} |")
    lines += ["", "## Per test patient (mean over seeds)", "",
              "| Patient | D1 AUROC | D2 AUROC | Clock only | Sensitivity | FAR / 24 h |", "|---|---|---|---|---|---|"]
    for k in sorted(by_subject, key=lambda k: subj_d2[k]):
        rs = by_subject[k]
        lines.append(f"| {k} | {subj_d1.get(k, float('nan')):.3f} | {subj_d2[k]:.3f} "
                     f"| {np.nanmean([r['clock_only_auroc'] for r in rs]):.3f} "
                     f"| {np.nanmean([r['sensitivity'] for r in rs]):.2f} | {np.nanmean([r['far_per_24h'] for r in rs]):.2f} |")
    lines += ["", "## False-alarm sets (setup chosen on all patients)", "",
              "| Seed | Set | Hours | False alarms | FAR / 24 h |", "|---|---|---|---|---|"]
    lines += [f"| {r['seed']} | {r['set']} | {r['hours']} | {r['false_alarms']} | {r['far_per_24h']:.2f} |" for r in fa_rows]
    (args.out / "d2_report.md").write_text("\n".join(lines) + "\n")

    print()
    print(f"VT-15 improvement:  {pf(vt15)}  D2 {mean_d2:.3f} ± {sd_d2:.3f} vs D1 {mean_d1:.3f} ({100 * rel:+.1f}%), "
          f"Wilcoxon p {wil_p:.3g}")
    print(f"VT-17 alarms:       {pf(vt17)}  sensitivity {mean_sens:.2f}, FAR {mean_far:.2f}/24h, max p {max_p:.3g}")
    print(f"Clock-only model:   {np.mean([per_seed[s]['mean_clock_only'] for s in seeds]):.3f}")
    print(f"D2 without clock:   {np.mean([per_seed[s]['mean_auroc_without_clock'] for s in seeds]):.3f}")
    print(f"Most common setup:  {max(setups, key=setups.get)} ({max(setups.values())} of {n_folds} folds)")
    for r in fa_rows:
        if r["seed"] == seeds[0]:
            print(f"False alarms, {r['set']}: {r['far_per_24h']:.2f}/24h")
    if dataset_check is not None:
        print(f"Dataset check AUROC: {dataset_check:.3f}")
    print(f"Report: {args.out / 'd2_report.md'}  ({(time.time() - t_start) / 60:.0f} min)")


if __name__ == "__main__":
    main()

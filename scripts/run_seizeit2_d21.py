"""D2.1 on SeizeIT2: the frozen design plus per-channel features, memory-efficient and resumable
(docs/evaluation_methods.md v1.28, Section 14.12).

The same computations as scripts/run_seizeit2.py (the frozen lockbox runner, unchanged), with one
difference, the D2.1 design: each behind-the-ear channel's own features (3 x 19) are added to the frozen
features, scaled by the same personal baseline, and columns with fewer than two distinct values in a
model's training data are dropped for that model (exactly as the `per_channel` challenger in
scripts/run_d2_plus.py).

    auroc    D2.1, leave one seizure out, mean per-patient AUROC, paired with the frozen design's
             lockbox AUROC for the same patients (results/lockbox/seizeit2_lockbox_progress.jsonl)
    alarms   D2.1 with the frozen alarm settings and thresholds chosen from each patient's training
             data only, on the same 20 patients as the frozen design's lockbox alarm result (v1.18)

Usage, from the repo root with .venv active:
    python scripts/run_seizeit2_d21.py --check [--design D]    development patients: must reproduce challenger D
                                                               (default per_channel; v1.29) at seed 0 exactly
    python scripts/run_seizeit2_d21.py --group lockbox --lockbox-run --part auroc     the lockbox run
    python scripts/run_seizeit2_d21.py --group lockbox --lockbox-run --part alarms    then the alarm part

The lockbox is refused unless the freeze-v1.13 and freeze-d2.1 Git tags exist.

Outputs: <out>/d21_seizeit2_<group>_<part>.md and .csv, and <out>/d21_seizeit2_<group>_progress.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon
from sklearn.metrics import roc_auc_score

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.config import load_config  # noqa: E402
from preictal.data.labels import INTERICTAL, PREICTAL, LabelRules  # noqa: E402
from preictal.data.seizeit2 import FEATURE_CODE, VERSION_TEXT, cohort  # noqa: E402
from preictal.evaluation.d2_plus import alarm_ppv_npv  # noqa: E402
from preictal.evaluation.metrics import (  # noqa: E402
    AlarmResult, Sequence, bootstrap_ci, chance_p_value, choose_threshold_bisect, evaluate_all,
)
from preictal.evaluation.patient_specific import inner_interictal_folds, patient_folds  # noqa: E402
from preictal.features.build_features import feature_version  # noqa: E402
from preictal.features.transforms import context_features  # noqa: E402
from preictal.models.model import ColumnSubsetModel, build_model, informative_columns, predict_proba  # noqa: E402
from preictal.models.train import TRAIN_CLASSES, blend_weights, load_windows  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

OTHERS_EVERY = 6                     # frozen: other patients' windows 30 s apart
CONTEXT_S = 600                      # frozen: 10 min context
TARGETS = (5.0, 1.0)
SMOOTHING, PERSISTENCE, WARMUP_S = 36, 6, 300.0
DESIGNS = {"per_channel": "D2.1: frozen design + per-channel features",
           "slow": "D2.1: frozen design + infra-slow features",
           "per_channel_slow": "D2.1: frozen design + per-channel and infra-slow features"}


def scale(M, ref):
    """Personal baseline: minus ref's median, over ref's interquartile range (floor 0.001)."""
    with np.errstate(all="ignore"):
        med = np.nanmedian(ref, axis=0)
        iqr = np.maximum(np.nanpercentile(ref, 75, axis=0) - np.nanpercentile(ref, 25, axis=0), 1e-3)
    return ((M - med) / iqr).astype(np.float32)


def fit_d21(X, y, w, seed, drop_empty=True):
    """With per-channel features, columns with fewer than two distinct values in this training data are dropped,
    as run_d2_plus.py does; the slow-only design is fitted on all columns, also as run_d2_plus.py does."""
    if not drop_empty:
        model = build_model(seed)
        model.fit(X, y, sample_weight=w)
        return model
    keep = informative_columns(X)
    model = build_model(seed)
    model.fit(X[:, keep], y, sample_weight=w)
    return ColumnSubsetModel(model, keep)


def auroc(y, s):
    y = np.asarray(y, bool)
    return float(roc_auc_score(y, s)) if y.any() and (~y).any() else float("nan")


def frozen_lockbox(repo: Path, part: str) -> dict:
    """The frozen design's lockbox results per patient (seed 0) from its progress file."""
    f = repo / "results" / "lockbox" / "seizeit2_lockbox_progress.jsonl"
    out = {}
    if f.exists():
        for line in f.read_text().splitlines():
            r = json.loads(line)
            if r.get("part") == part and int(r.get("seed", 0)) == 0:
                out[r["subject"]] = r
    return out


def alarm_subset(repo: Path) -> set[str] | None:
    """The 20 patients of the frozen design's lockbox alarm result (v1.18), from its report."""
    md = repo / "results" / "lockbox" / "seizeit2_lockbox_alarms.md"
    if md.exists():
        m = re.search(r"evaluation methods v1\.18\): (.+?)\.\s*$", md.read_text(), re.M)
        if m:
            return {s.strip() for s in m.group(1).split(",")}
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--group", choices=["development", "lockbox"], default="development")
    ap.add_argument("--lockbox-run", action="store_true")
    ap.add_argument("--part", choices=["auroc", "alarms"], default="auroc")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0])
    ap.add_argument("--check", action="store_true",
                    help="development patients: the AUROC part must reproduce run_d2_plus.py's per_channel arm")
    ap.add_argument("--features", type=Path, default=REPO / "data" / "processed" / "features_seizeit2")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--design", choices=list(DESIGNS), default="per_channel",
                    help="which challenger D2.1 is (evaluation methods v1.29); the check compares with that arm")
    args = ap.parse_args()
    DESIGN = DESIGNS[args.design]
    use_pc, use_slow = "per_channel" in args.design, "slow" in args.design
    if args.check:
        args.group, args.part = "development", "auroc"
    if args.group == "lockbox":
        tags = subprocess.run(["git", "tag", "-l", "freeze-d2.1"], cwd=REPO, capture_output=True, text=True).stdout
        if not args.lockbox_run or "freeze-d2.1" not in tags:
            sys.exit("Refusing to touch the lockbox: D2.1 runs there only after its freeze "
                     "(needs --lockbox-run and the freeze-d2.1 Git tag).")
    args.out = args.out or REPO / "results" / ("lockbox" if args.group == "lockbox" else "seizeit2_dev")
    args.out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    step_s = cfg["windows"]["step_s"]
    version = feature_version(cfg, VERSION_TEXT, FEATURE_CODE)
    _, test_subjects, pool = cohort(REPO, args.group, args.lockbox_run)
    tl_info = json.loads((args.features / "timelines.json").read_text())
    kw = dict(sph_s=rules.sph_s, horizon_s=rules.preictal_start_s, refractory_s=cfg["alarm"]["refractory_min"] * 60,
              smoothing=SMOOTHING, persistence=PERSISTENCE)
    n_cand = cfg["alarm"]["threshold_candidates"]
    subset = None
    if args.part == "alarms" and args.group == "lockbox":
        subset = alarm_subset(REPO)
        if subset is None:
            sys.exit("Couldn't read the frozen design's 20 lockbox alarm patients from "
                     "results/lockbox/seizeit2_lockbox_alarms.md")

    print("Loading features...")
    # only this run's patients and training pool are loaded (development runs never load the lockbox)
    W = load_windows(args.features, ("seizeit2",), subjects=pool, version=version, keep_per_channel=use_pc)
    extra = []
    if use_slow:
        sys.path.insert(0, str(REPO / "scripts"))
        from run_d2_plus import load_slow
        extra.append(load_slow(W, args.features, ("seizeit2",)).astype(np.float32))
    if use_pc:
        extra.append(W.per_channel.reshape(len(W.y), -1).astype(np.float32))
        W.per_channel = None
    EXTRA = np.hstack(extra)
    missing = sorted(pool - set(W.subjects))
    if missing:
        sys.exit(f"No features for {len(missing)} patients (e.g. {missing[0]}); run extract_seizeit2.py first")
    print(f"  {len(W.y):,} windows from {len(W.subjects)} patients")

    def patient_matrix(rows):
        """Frozen features + 10 min context (never crossing patients) + the design's extra features, in the
        same column order as run_d2_plus.py (slow, then per-channel)."""
        ctx = context_features(W.X[rows], W.timeline[rows], W.t_end[rows], CONTEXT_S)
        return np.hstack([W.X[rows], ctx, EXTRA[rows]]).astype(np.float32)

    print("Preparing the other patients' training rows...")
    parts_X, parts_y, parts_s = [], [], []
    codes = [c for c, s in enumerate(W.subjects) if s in pool]
    it = tqdm(codes, desc="  patients", leave=False) if tqdm else codes
    for code in it:
        rows = np.flatnonzero(W.subject == code)
        M = patient_matrix(rows)
        ref = W.y[rows] == INTERICTAL
        S = scale(M, M[ref]) if ref.any() else M
        keep = np.isin(W.y[rows], TRAIN_CLASSES) & (np.round(W.t_end[rows] / 5.0).astype(np.int64) % OTHERS_EVERY == 0)
        parts_X.append(S[keep]); parts_y.append(W.y[rows][keep]); parts_s.append(np.full(keep.sum(), code, np.int32))
    O_X, O_y, O_s = np.vstack(parts_X), np.concatenate(parts_y), np.concatenate(parts_s)
    del parts_X
    print(f"  {len(O_y):,} training rows from {len(codes)} patients")

    patients = []
    for code, subject in enumerate(W.subjects):
        if subject not in test_subjects or (subset is not None and subject not in subset):
            continue
        rows = np.flatnonzero(W.subject == code)
        events = [(tl, on) for tl in np.unique(W.timeline[rows]) for on in tl_info[W.timelines[tl]]["eligible_onsets"]]
        if len(events) >= 2 and (W.y[rows] == INTERICTAL).sum() * step_s >= 3600:
            patients.append((subject, code, rows, events))
    print(f"{len(patients)} patients; part: {args.part}; seeds {args.seeds}")

    tag = "d21" if args.design == "per_channel" else f"d21_{args.design}"
    progress = args.out / f"{tag}_seizeit2_{args.group if not args.check else 'check'}_progress.jsonl"
    if args.check:
        progress.unlink(missing_ok=True)
    done = {}
    if progress.exists():
        for line in progress.read_text().splitlines():
            r = json.loads(line)
            done[(r["part"], r["subject"], r["seed"])] = r

    def seqs_for(rel, scores, t, y, tl, onsets=()):
        out = []
        order = np.lexsort((t[rel], tl[rel]))
        rel, scores = rel[order], scores[order]
        for c in np.unique(tl[rel]):
            m = tl[rel] == c
            on = np.array(onsets, float)
            out.append(Sequence("", t[rel][m], scores[m], y[rel][m], on, on))
        return out

    it = tqdm(patients, desc="patients") if tqdm else patients
    for subject, code, rows, events in it:
        if all((args.part, subject, s) in done for s in args.seeds):
            continue
        t, y, tl = W.t_end[rows], W.y[rows], W.timeline[rows]
        M = patient_matrix(rows)
        others = O_s != code
        Xo, yo, so = O_X[others], O_y[others], O_s[others]
        folds = [(i, tr, te) for i, tr, te in patient_folds(t, y, tl, events, rules.preictal_start_s, rules.sph_s,
                                                             rules.interictal_gap_s, train_labels=y)
                 if (y[tr] == PREICTAL).any() and (y[tr] == INTERICTAL).any()]
        if not folds:
            continue
        events_sorted = sorted(events)

        def scaled(ref_rel):
            ref = ref_rel[y[ref_rel] == INTERICTAL]
            return scale(M, M[ref])

        def train(rel, P, seed):
            rel = rel[np.isin(y[rel], TRAIN_CLASSES)]
            wg, wp = blend_weights(yo, so, y[rel], 0.5)
            return fit_d21(np.vstack([Xo, P[rel]]), np.concatenate([yo, y[rel]]), np.concatenate([wg, wp]), seed,
                           drop_empty=use_pc)

        for seed in args.seeds:
            if (args.part, subject, seed) in done:
                continue
            if args.part == "auroc":
                preds, labels = [], []
                for i, tr, test in folds:
                    P = scaled(tr)
                    labels.append(y[test])
                    preds.append(predict_proba(train(tr, P, seed), P[test])[:, 0])
                lab = np.concatenate(labels)
                pi = np.isin(lab, (PREICTAL, INTERICTAL))
                rec = {"part": "auroc", "subject": subject, "seed": seed, "seizures": len(events), "folds": len(folds),
                       "d21": auroc(lab[pi] == PREICTAL, np.concatenate(preds)[pi])}
            else:
                totals = {tg: AlarmResult() for tg in TARGETS}
                true_alarms = {tg: 0 for tg in TARGETS}
                for i, tr, test in folds:
                    tl_e, onset = events_sorted[i]
                    pre_rel = np.flatnonzero((tl == tl_e) & (t >= onset - rules.preictal_start_s - WARMUP_S)
                                             & (t <= onset - rules.sph_s))
                    chunk = test[y[test] == INTERICTAL]
                    inner_seqs = []
                    for inner_train, inner_chunk in inner_interictal_folds(t, y, tl, tr):
                        P_in = scaled(inner_train)
                        m = train(inner_train, P_in, seed)
                        inner_seqs += seqs_for(inner_chunk, predict_proba(m, P_in[inner_chunk])[:, 0], t, y, tl)
                    P = scaled(tr)
                    model = train(tr, P, seed)
                    pre = seqs_for(pre_rel, predict_proba(model, P[pre_rel])[:, 0], t, y, tl, [onset])
                    inter = seqs_for(chunk, predict_proba(model, P[chunk])[:, 0], t, y, tl)
                    for tg in TARGETS:
                        thr, _ = choose_threshold_bisect(inner_seqs, tg, step_s, n_cand, **kw)
                        warned = evaluate_all(pre, thr, step_s, **kw)
                        fa = evaluate_all(inter, thr, step_s, **kw)
                        true_alarms[tg] += warned.n_alarms - warned.n_false
                        totals[tg] = totals[tg].add(AlarmResult(
                            n_events=1, n_predicted=min(warned.n_predicted, 1), n_alarms=fa.n_alarms,
                            n_false=fa.n_false, far_hours=fa.far_hours, n_windows=fa.n_windows,
                            n_warning_windows=fa.n_warning_windows, warning_times=warned.warning_times))
                rec = {"part": "alarms", "subject": subject, "seed": seed, "seizures": len(folds),
                       "results": {f"d21|{tg:g}": {"warned": r.n_predicted, "false_alarms": r.n_false,
                                                    "hours": r.far_hours, "true_alarms": true_alarms[tg]}
                                   for tg, r in totals.items()}}
            done[(args.part, subject, seed)] = rec
            with open(progress, "a") as fh:
                fh.write(json.dumps(rec) + "\n")

    names = {s for s, *_ in patients}
    if args.check:
        ref = {}
        f = REPO / "results" / "d2_plus" / "seizeit2" / "progress.jsonl"
        for line in (f.read_text().splitlines() if f.exists() else []):
            r = json.loads(line)
            if r["arm"] == args.design and not r.get("alarms"):
                ref[(r["subject"], r["seed"])] = r["auroc"]
        compared = same = 0
        for (part, s, seed), r in sorted(done.items()):
            if (s, seed) not in ref:
                continue
            compared += 1
            ok = abs(r["d21"] - ref[(s, seed)]) <= 1e-9
            same += ok
            print(f"{s:22s} seed {seed}: new {r['d21']:.6f}  {args.design} challenger {ref[(s, seed)]:.6f}  "
                  f"{'same' if ok else 'DIFFERENT'}")
        print(f"\nCHECK PASSED: {compared} of {compared} identical" if compared and same == compared else
              f"\nCHECK FAILED: {same} of {compared} identical" + ("" if compared else " (nothing was compared)"))
        print(f"Run time: {(time.time() - t_start) / 60:.1f} min")
        return

    recs = [r for (p, s, seed), r in done.items() if p == args.part and s in names and seed in args.seeds]
    stem = args.out / f"{tag}_seizeit2_{args.group}_{args.part}"
    lines = [f"# SeizeIT2 {args.group}: {DESIGN}, {args.part}", "",
             f"Generated {datetime.now().isoformat(timespec='seconds')} · seeds {args.seeds} · {len(names)} patients · "
             "docs/evaluation_methods.md v1.28, Section 14.12.", ""]
    frozen = frozen_lockbox(REPO, args.part) if args.group == "lockbox" else {}
    if args.part == "auroc":
        rows_csv = []
        for r in sorted(recs, key=lambda r: r["subject"]):
            fz = frozen.get(r["subject"], {}).get("general_personal", float("nan"))
            rows_csv.append({"subject": r["subject"], "seed": r["seed"], "seizures": r["seizures"], "folds": r["folds"],
                             "d21": r["d21"], "frozen": fz})
        with open(stem.with_suffix(".csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_csv[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows_csv)
        per = defaultdict(list)
        for r in rows_csv:
            per[r["subject"]].append((r["d21"], r["frozen"]))
        d21 = np.array([np.nanmean([a for a, _ in v]) for v in per.values()])
        fz = np.array([np.nanmean([b for _, b in v]) for v in per.values()])
        ci = bootstrap_ci(list(d21), 1000, 0)
        lines += ["| Design | Patients | Mean AUROC | 95% CI |", "|---|---|---|---|",
                  f"| {DESIGN} | {len(d21)} | {np.nanmean(d21):.3f} | {ci[0]:.3f}–{ci[1]:.3f} |"]
        ok = ~np.isnan(fz)
        if ok.any():
            cf = bootstrap_ci(list(fz[ok]), 1000, 0)
            diff = d21[ok] - fz[ok]
            cd = bootstrap_ci(list(diff), 1000, 0)
            try:
                p = float(wilcoxon(d21[ok], fz[ok]).pvalue)
            except ValueError:
                p = float("nan")
            lines += [f"| Frozen design (same patients, lockbox run of v1.18) | {ok.sum()} | {np.mean(fz[ok]):.3f} "
                      f"| {cf[0]:.3f}–{cf[1]:.3f} |", "",
                      f"**Paired:** D2.1 minus frozen {np.mean(diff):+.3f} (95% CI {cd[0]:+.3f} to {cd[1]:+.3f}); "
                      f"D2.1 higher in {(diff > 0).sum()} of {ok.sum()} patients; Wilcoxon p = {p:.3g}.", "",
                      "**Verdict by the rule fixed in v1.28 (Section 14.12):** "
                      + ("CONFIRMED better on new patients (mean difference positive, 95% interval excludes zero)."
                         if np.mean(diff) > 0 and cd[0] > 0 else
                         "NOT CONFIRMED (the 95% interval of the difference includes zero, or the difference isn't "
                         "positive); the frozen design remains the reported final design.")]
            print(f"D2.1 {np.nanmean(d21):.3f} vs frozen {np.mean(fz[ok]):.3f}: {np.mean(diff):+.3f}, "
                  f"higher in {(diff > 0).sum()} of {ok.sum()}, p = {p:.3g}")
        else:
            print(f"D2.1 {np.nanmean(d21):.3f} (95% CI {ci[0]:.3f}-{ci[1]:.3f}) on {len(d21)} patients")
    else:
        rows_csv = []
        lines += ["| Design | Target | Seizures warned | False alarms / 24 h | Chance | p | Alarm PPV | NPV |",
                  "|---|---|---|---|---|---|---|---|"]
        for tg in TARGETS:
            key = f"d21|{tg:g}"
            n_ev = sum(r["seizures"] for r in recs)
            n_w = sum(r["results"][key]["warned"] for r in recs)
            fa = sum(r["results"][key]["false_alarms"] for r in recs)
            ta = sum(r["results"][key]["true_alarms"] for r in recs)
            hours = sum(r["results"][key]["hours"] for r in recs)
            far = 24 * fa / hours if hours else float("nan")
            c, p = chance_p_value(n_w, n_ev, far, rules.preictal_start_s - rules.sph_s)
            pn = alarm_ppv_npv(n_ev, n_w, fa, hours, true_alarms=ta)
            rows_csv.append({"design": "d21", "far_target": tg, "seizures": n_ev, "warned": n_w, "false_alarms": fa,
                             "true_alarms": ta, "interictal_hours": round(hours, 2), "far_per_24h": far, "chance": c,
                             "p": p, "ppv": pn["ppv"], "npv": pn["npv"]})
            lines.append(f"| {DESIGN} | ≤ {tg:g} | {n_w}/{n_ev} ({n_w / n_ev:.2f}) | {far:.2f} | {c:.3f} | {p:.3g} "
                         f"| {pn['ppv']:.3f} | {pn['npv']:.4f} |")
            print(f"D2.1 ≤{tg:g}/24h: warned {n_w}/{n_ev} ({n_w / n_ev:.2f}), FAR {far:.2f}, chance {c:.3f}, p {p:.3g}, "
                  f"PPV {pn['ppv']:.3f}")
            fr = [frozen[s] for s in names if s in frozen]
            if fr:
                fkey = f"general_personal|{tg:g}"
                fn_ev = sum(r["seizures"] for r in fr)
                fn_w = sum(r["results"][fkey]["warned"] for r in fr)
                ffa = sum(r["results"][fkey]["false_alarms"] for r in fr)
                fh_ = sum(r["results"][fkey]["hours"] for r in fr)
                ffar = 24 * ffa / fh_ if fh_ else float("nan")
                fc, fp = chance_p_value(fn_w, fn_ev, ffar, rules.preictal_start_s - rules.sph_s)
                fpn = alarm_ppv_npv(fn_ev, fn_w, ffa, fh_)
                lines.append(f"| Frozen design (same patients, v1.18) | ≤ {tg:g} | {fn_w}/{fn_ev} ({fn_w / fn_ev:.2f}) "
                             f"| {ffar:.2f} | {fc:.3f} | {fp:.3g} | {fpn['ppv']:.3f} | {fpn['npv']:.4f} |")
        with open(stem.with_suffix(".csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_csv[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows_csv)
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print(f"Report: {stem.with_suffix('.md')}  ({(time.time() - t_start) / 3600:.1f} h this session)")


if __name__ == "__main__":
    main()

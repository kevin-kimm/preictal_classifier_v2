"""Continuous personalization, simulated forward in time (docs/evaluation_methods.md v1.19).

For each SeizeIT2 development patient, the frozen design's recipe (other patients + this
patient, feature set v2, personal baseline, 10 min context, no time of day, frozen alarm
settings) is re-run as a device would: calibrate on the first 6 h, predict with the general
model until the first seizure, then retrain 1 h after every seizure using only what was known
by then, and predict until the next one (src/preictal/evaluation/learning_curve.py). Each step
is scored only on the time after it was trained. A general model with the same personal
baseline but no personal seizures is scored at every step for comparison.

Adaptive thresholds (evaluation methods v1.20, a v3 development experiment): with --adaptive,
every step's alarms are also evaluated with a threshold that is recalibrated every 6 h on the
wearer's recent confirmed-normal EEG (the 24 h ending 4 h before recalibration, after the last
retraining, at least 2 h of it), alongside the fixed threshold.

Usage, from the repo root with .venv active (after the lockbox alarm run has finished):
    python scripts/run_learning_curve.py
    python scripts/run_learning_curve.py --adaptive --tag _adaptive
    python scripts/run_learning_curve.py --adaptive --log-alarms --tag _breakdown
    python scripts/run_learning_curve.py --adaptive --arms --tag _arms
    python scripts/run_learning_curve.py --adaptive --arms --recipes --tag _recipes
                     (v1.23: also trains, at every step, a blend with 75% personal weight and a
                      patient-only model, alongside the current 50% blend)
                     (v1.22: also evaluates faster recalibration and a stricter first day after each
                      seizure, as comparison arms with the same models)
                     (v1.21: also writes every alarm, with its timing, to alarm_log<tag>.csv)

Outputs: results/seizeit2_dev/learning_curve.md and .csv, results/figures/learning_curve.png
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.alarm.alarm import alarm_times  # noqa: E402
from preictal.config import load_config  # noqa: E402
from preictal.data.labels import EXCLUDED, INTERICTAL, PREICTAL, LabelRules  # noqa: E402
from preictal.data.seizeit2 import FEATURE_CODE, VERSION_TEXT, cohort  # noqa: E402
from preictal.evaluation.learning_curve import forward_steps  # noqa: E402
from preictal.evaluation.metrics import (  # noqa: E402
    Sequence, bootstrap_ci, chance_p_value, choose_threshold_bisect, evaluate_all, evaluate_all_varying,
)
from preictal.evaluation.patient_specific import inner_interictal_folds  # noqa: E402
from preictal.features.build_features import feature_version  # noqa: E402
from preictal.features.transforms import context_features  # noqa: E402
from preictal.models.model import ColumnSubsetModel, build_model, informative_columns, predict_proba  # noqa: E402
from preictal.models.train import TRAIN_CLASSES, blend_weights, load_windows, sample_weights  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

OTHERS_EVERY, CONTEXT_S = 6, 600
TARGETS = (5.0, 1.0)
SMOOTHING, PERSISTENCE, WARMUP_S = 36, 6, 300.0
MODELS = ("personal", "general")
RECIPES = ("personal", "personal75", "patient_only", "general")
DISPLAY = {"personal": "learning device", "personal75": "learning device, 75% personal",
           "patient_only": "learning device, patient only", "general": "never learns"}
LABELS = {"personal": "Device that learns each seizure (frozen recipe, retrained after every seizure)",
          "personal75": "Learning device, 75% personal weight",
          "patient_only": "Learning device, this patient's data only",
          "general": "General model with the personal baseline only (never learns seizures)"}


def scale(M, ref):
    with np.errstate(all="ignore"):
        med = np.nanmedian(ref, axis=0)
        iqr = np.maximum(np.nanpercentile(ref, 75, axis=0) - np.nanpercentile(ref, 25, axis=0), 1e-3)
    return ((M - med) / iqr).astype(np.float32)


def fit(X, y, w, seed):
    model = build_model(seed)
    model.fit(X, y, sample_weight=w)
    return model


def auroc(y, s):
    y = np.asarray(y, bool)
    return float(roc_auc_score(y, s)) if y.any() and (~y).any() else float("nan")


def num(r, key, missing=float("nan")):
    """A result from a row, as a float; missing or blank values (a recipe that couldn't be trained) give `missing`."""
    v = r.get(key, missing)
    if v is None or v == "":
        return missing
    try:
        return float(v)
    except (TypeError, ValueError):
        return missing


def read_rows(path):
    """Rows of a learning-curve CSV, with numbers as numbers (for --summarize-only)."""
    rows = []
    for r in csv.DictReader(open(path)):
        row = {"subject": r["subject"], "k": int(float(r["k"]))}
        for key, v in r.items():
            if key not in ("subject", "k") and v not in ("", None):     # blank = not computed at that step
                row[key] = num(r, key)
        rows.append(row)
    return rows


def bin_of(k):
    return str(k) if k < 5 else "5+"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--features", type=Path, default=REPO / "data" / "processed" / "features_seizeit2")
    ap.add_argument("--out", type=Path, default=REPO / "results" / "seizeit2_dev")
    ap.add_argument("--adaptive", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--log-alarms", action="store_true")
    ap.add_argument("--arms", action="store_true", help="v1.22 comparison arms (needs --adaptive)")
    ap.add_argument("--recipes", action="store_true", help="v1.23: personal75 and patient_only recipes too")
    ap.add_argument("--summarize-only", action="store_true",
                    help="rebuild the report and figure from an existing learning_curve<tag>.csv, without rerunning")
    args = ap.parse_args()
    RECAL_S, REF_S, MIN_REF_S = 6 * 3600.0, 24 * 3600.0, 2 * 3600.0
    global MODELS
    if args.recipes:
        MODELS = RECIPES
    FAST_EVERY_S, FAST_LAG_S, FAST_MIN_S, STRICT_S = 3600.0, 3600.0, 3600.0, 24 * 3600.0
    ARMS = ("adaptive", "fast", "strict24", "fast_strict24")
    if args.arms and not args.adaptive:
        sys.exit("--arms needs --adaptive")
    args.out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    step_s = cfg["windows"]["step_s"]
    version = feature_version(cfg, VERSION_TEXT, FEATURE_CODE)
    _, test_subjects, pool = cohort(REPO, "development")
    tl_info = json.loads((args.features / "timelines.json").read_text())
    kw = dict(sph_s=rules.sph_s, horizon_s=rules.preictal_start_s, refractory_s=cfg["alarm"]["refractory_min"] * 60,
              smoothing=SMOOTHING, persistence=PERSISTENCE)
    n_cand = cfg["alarm"]["threshold_candidates"]

    if args.summarize_only:
        rows_out, alarm_log = read_rows(args.out / f"learning_curve{args.tag}.csv"), []
        print(f"Rebuilding the report from learning_curve{args.tag}.csv ({len(rows_out)} steps)")
    else:
        print("Loading features...")
        W = load_windows(args.features, ("seizeit2",), version=version, keep_per_channel=False)

        def patient_matrix(rows):
            ctx = context_features(W.X[rows], W.timeline[rows], W.t_end[rows], CONTEXT_S)
            return np.hstack([W.X[rows], ctx]).astype(np.float32)

        print("Preparing the other development patients' training rows...")
        parts_X, parts_y, parts_s = [], [], []
        for code in [c for c, s in enumerate(W.subjects) if s in pool]:
            rows = np.flatnonzero(W.subject == code)
            M = patient_matrix(rows)
            ref = W.y[rows] == INTERICTAL
            S = scale(M, M[ref]) if ref.any() else M
            keep = np.isin(W.y[rows], TRAIN_CLASSES) & (np.round(W.t_end[rows] / 5.0).astype(np.int64) % OTHERS_EVERY == 0)
            parts_X.append(S[keep]); parts_y.append(W.y[rows][keep]); parts_s.append(np.full(keep.sum(), code, np.int32))
        O_X, O_y, O_s = np.vstack(parts_X), np.concatenate(parts_y), np.concatenate(parts_s)
        del parts_X

        def seqs_for(rel, scores, t, y, tl, onsets=()):
            out = []
            order = np.lexsort((t[rel], tl[rel]))
            rel, scores = rel[order], scores[order]
            for c in np.unique(tl[rel]):
                m = tl[rel] == c
                on = np.array(onsets, float)
                out.append(Sequence("", t[rel][m], scores[m], y[rel][m], on, on))
            return out

        rows_out, alarm_log = [], []

        def log_alarms(seqs, thr, *, subject, k, model, mode, target, true_window, t_first, cutoff, recal, rows_p, t_p):
            """Every alarm in these sequences, with when it happened in the device's life (v1.21)."""
            order = np.argsort(t_p)
            for s in seqs:
                th = thr(s.times) if callable(thr) else thr
                for a in alarm_times(s.times, s.scores, th, kw["refractory_s"], SMOOTHING, PERSISTENCE):
                    if true_window is not None and not (true_window[0] <= a <= true_window[1]):
                        continue
                    j = order[np.searchsorted(t_p[order], a)]
                    g = rows_p[j]
                    last_recal = max([r for r in recal if r <= a], default=cutoff)
                    alarm_log.append({
                        "subject": subject, "k": k, "model": model, "thresholds": mode, "target": target,
                        "false": true_window is None, "t": round(float(a), 1),
                        "recording": W.recordings[W.recording[g]] if W.recordings is not None else "",
                        "s_into_recording": round(float(W.starts[g] + L), 1) if W.starts is not None else float("nan"),
                        "h_since_start": round((a - t_first) / 3600, 3), "h_since_retraining": round((a - cutoff) / 3600, 3),
                        "h_since_recalibration": round((a - last_recal) / 3600, 3)})

        L = cfg["windows"]["length_s"]
        subjects = [(c, s) for c, s in enumerate(W.subjects) if s in test_subjects]
        it = tqdm(subjects, desc="patients") if tqdm else subjects
        for code, subject in it:
            rows = np.flatnonzero(W.subject == code)
            if len(np.unique(W.timeline[rows])) != 1:
                continue
            t, y, tl = W.t_end[rows], W.y[rows], W.timeline[rows]
            onsets = sorted(tl_info[W.timelines[tl[0]]]["eligible_onsets"])
            steps = forward_steps(t, y, onsets, rules.preictal_start_s, rules.sph_s, rules.interictal_gap_s)
            if not steps:
                continue
            M = patient_matrix(rows)
            others = O_s != code
            Xo, yo, so = O_X[others], O_y[others], O_s[others]
            general = fit(Xo, yo, sample_weights(yo, so), args.seed)

            for st in steps:
                base = st.baseline if len(st.baseline) else st.train[~np.isin(y[st.train], (PREICTAL,))]
                if len(base) == 0:
                    continue
                P = scale(M, M[base])
                def train_recipe(recipe, rel, P_):
                    """One learning-device recipe trained on rel (v1.23); None if it can't be trained."""
                    rel = rel[np.isin(y[rel], TRAIN_CLASSES)]
                    if recipe == "patient_only":
                        if not ((y[rel] == PREICTAL).any() and (y[rel] == INTERICTAL).any()):
                            return None
                        keep = informative_columns(P_[rel])
                        return ColumnSubsetModel(fit(P_[rel][:, keep], y[rel],
                                                     sample_weights(y[rel], np.zeros(len(rel), dtype=int)), args.seed),
                                                 keep)
                    wg, wp = blend_weights(yo, so, y[rel], 0.75 if recipe == "personal75" else 0.5)
                    return fit(np.vstack([Xo, P_[rel]]), np.concatenate([yo, y[rel]]), np.concatenate([wg, wp]),
                               args.seed)

                models = {"general": general}
                for recipe in [m for m in MODELS if m != "general"]:
                    if st.k == 0:
                        models[recipe] = general                     # nothing learned yet: the device is the general model
                    else:
                        m_r = train_recipe(recipe, st.train, P)
                        if m_r is not None:
                            models[recipe] = m_r
                test = st.test
                pre_mask = y[test] == PREICTAL
                rec = {"subject": subject, "k": st.k, "test_preictal": int(pre_mask.sum()),
                       "test_interictal": int((~pre_mask).sum())}
                since = (t[test[~pre_mask]] - st.cutoff) / 3600
                rec["inter_h_0_6"] = float(((since >= 0) & (since < 6)).sum() * step_s / 3600)
                rec["inter_h_6_24"] = float(((since >= 6) & (since < 24)).sum() * step_s / 3600)
                rec["inter_h_24p"] = float((since >= 24).sum() * step_s / 3600)
                for name, model in models.items():
                    rec[f"auroc_{name}"] = auroc(pre_mask, predict_proba(model, P[test])[:, 0])
                    # threshold from what the device knew at this step
                    if st.k == 0 or name == "general":
                        ref_rows = st.baseline if st.k == 0 else st.train[y[st.train] == INTERICTAL]
                        inner = seqs_for(ref_rows, predict_proba(model, P[ref_rows])[:, 0], t, y, tl) if len(ref_rows) else []
                    else:
                        inner = []
                        for inner_train, inner_chunk in inner_interictal_folds(t, y, tl, st.train):
                            ib = inner_train[y[inner_train] == INTERICTAL]
                            if len(ib) == 0:
                                continue
                            P_in = scale(M, M[ib])
                            m_in = train_recipe(name, inner_train, P_in)
                            if m_in is None:
                                continue
                            inner += seqs_for(inner_chunk, predict_proba(m_in, P_in[inner_chunk])[:, 0], t, y, tl)
                    pre_rel = np.flatnonzero((t > st.cutoff) & (t >= st.next_onset - rules.preictal_start_s - WARMUP_S)
                                             & (t <= st.next_onset - rules.sph_s))
                    inter_rel = test[~pre_mask]
                    for tg in TARGETS:
                        key = f"{name}_{tg:g}"
                        if not inner or len(pre_rel) == 0:
                            rec[f"warned_{key}"], rec[f"fa_{key}"], rec[f"hours_{key}"] = float("nan"), 0, 0.0
                            if args.adaptive:
                                rec[f"warned_{key}_adaptive"], rec[f"fa_{key}_adaptive"] = float("nan"), 0
                                rec[f"hours_{key}_adaptive"], rec[f"recalibrations_{key}"] = 0.0, 0
                            continue
                        thr, _ = choose_threshold_bisect(inner, tg, step_s, n_cand, **kw)
                        warned = evaluate_all(seqs_for(pre_rel, predict_proba(model, P[pre_rel])[:, 0], t, y, tl,
                                                       [st.next_onset]), thr, step_s, **kw)
                        fa = (evaluate_all(seqs_for(inter_rel, predict_proba(model, P[inter_rel])[:, 0], t, y, tl),
                                           thr, step_s, **kw) if len(inter_rel) else None)
                        rec[f"warned_{key}"] = min(warned.n_predicted, 1)
                        rec[f"fa_{key}"] = fa.n_false if fa else 0
                        rec[f"hours_{key}"] = fa.far_hours if fa else 0.0
                        common = dict(subject=subject, k=st.k, model=name, target=tg, t_first=float(t.min() - L),
                                      cutoff=st.cutoff, rows_p=rows, t_p=t)
                        if args.log_alarms:
                            pre_seqs = seqs_for(pre_rel, predict_proba(model, P[pre_rel])[:, 0], t, y, tl, [st.next_onset])
                            win = (st.next_onset - rules.preictal_start_s, st.next_onset - rules.sph_s)
                            log_alarms(pre_seqs, thr, mode="fixed", true_window=win, recal=[], **common)
                            if len(inter_rel):
                                log_alarms(seqs_for(inter_rel, predict_proba(model, P[inter_rel])[:, 0], t, y, tl), thr,
                                           mode="fixed", true_window=None, recal=[], **common)
                        if args.adaptive:
                            # recalibrate every 6 h on recent confirmed-normal EEG seen since retraining (never trained on)
                            s_inter = predict_proba(model, P[inter_rel])[:, 0] if len(inter_rel) else np.array([])
                            times_k, thr_k = [st.cutoff], [thr]
                            r = st.cutoff + RECAL_S
                            while r < st.next_onset:
                                hi = r - rules.interictal_gap_s
                                ref = (t[inter_rel] > max(st.cutoff, hi - REF_S)) & (t[inter_rel] <= hi) if len(inter_rel) \
                                    else np.zeros(0, bool)
                                if ref.sum() * step_s >= MIN_REF_S:
                                    new_thr, _ = choose_threshold_bisect(seqs_for(inter_rel[ref], s_inter[ref], t, y, tl),
                                                                         tg, step_s, n_cand, **kw)
                                    times_k.append(r)
                                    thr_k.append(new_thr)
                                r += RECAL_S
                            times_k, thr_k = np.array(times_k), np.array(thr_k)

                            def thr_at(tt, times_k=times_k, thr_k=thr_k):
                                return thr_k[np.clip(np.searchsorted(times_k, tt, side="right") - 1, 0, len(thr_k) - 1)]

                            wa = evaluate_all_varying(seqs_for(pre_rel, predict_proba(model, P[pre_rel])[:, 0], t, y, tl,
                                                               [st.next_onset]), thr_at, step_s, **kw)
                            fa_a = (evaluate_all_varying(seqs_for(inter_rel, s_inter, t, y, tl), thr_at, step_s, **kw)
                                    if len(inter_rel) else None)
                            if args.log_alarms:
                                log_alarms(seqs_for(pre_rel, predict_proba(model, P[pre_rel])[:, 0], t, y, tl,
                                                    [st.next_onset]), thr_at, mode="adaptive",
                                           true_window=(st.next_onset - rules.preictal_start_s,
                                                        st.next_onset - rules.sph_s), recal=list(times_k[1:]), **common)
                                if len(inter_rel):
                                    log_alarms(seqs_for(inter_rel, s_inter, t, y, tl), thr_at, mode="adaptive",
                                               true_window=None, recal=list(times_k[1:]), **common)
                            rec[f"warned_{key}_adaptive"] = min(wa.n_predicted, 1)
                            rec[f"fa_{key}_adaptive"] = fa_a.n_false if fa_a else 0
                            rec[f"hours_{key}_adaptive"] = fa_a.far_hours if fa_a else 0.0
                            rec[f"recalibrations_{key}"] = len(thr_k) - 1
                    if args.arms:
                        # v1.22 arms: the same model, different threshold schedules
                        def schedule(rel_ref, s_ref, thr0, tg, lag, every, min_ref):
                            times_k, thr_k = [st.cutoff], [thr0]
                            r = st.cutoff + every
                            while r < st.next_onset:
                                hi = r - lag
                                m = (t[rel_ref] > max(st.cutoff, hi - REF_S)) & (t[rel_ref] <= hi)
                                if m.sum() * step_s >= min_ref:
                                    times_k.append(r)
                                    thr_k.append(choose_threshold_bisect(seqs_for(rel_ref[m], s_ref[m], t, y, tl),
                                                                         tg, step_s, n_cand, **kw)[0])
                                r += every
                            return np.array(times_k), np.array(thr_k)

                        def at(times_k, thr_k):
                            return lambda tt: thr_k[np.clip(np.searchsorted(times_k, tt, side="right") - 1, 0,
                                                            len(thr_k) - 1)]

                        usable = bool(inner) and len(pre_rel) > 0
                        if usable:
                            s_pre = predict_proba(model, P[pre_rel])[:, 0]
                            s_int = predict_proba(model, P[inter_rel])[:, 0] if len(inter_rel) else np.array([])
                            # fast recalibration may use any non-seizure EEG at least 1 h old (never preictal by then)
                            cal = np.flatnonzero((t > st.cutoff) & (t < st.next_onset)
                                                 & np.isin(y, (INTERICTAL, EXCLUDED)))
                            s_cal = predict_proba(model, P[cal])[:, 0] if len(cal) else np.array([])
                            fn = {}
                            for tg in TARGETS:
                                thr0 = choose_threshold_bisect(inner, tg, step_s, n_cand, **kw)[0]
                                fn[(tg, "adaptive")] = at(*schedule(inter_rel, s_int, thr0, tg, rules.interictal_gap_s,
                                                                     RECAL_S, MIN_REF_S)) if len(inter_rel) else \
                                    (lambda tt, v=thr0: np.full(len(tt), v))
                                fn[(tg, "fast")] = at(*schedule(cal, s_cal, thr0, tg, FAST_LAG_S, FAST_EVERY_S,
                                                                 FAST_MIN_S)) if len(cal) else \
                                    (lambda tt, v=thr0: np.full(len(tt), v))
                            for base in ("adaptive", "fast"):
                                lo, hi_ = fn[(5.0, base)], fn[(1.0, base)]
                                fn[(5.0, f"{base}_strict24" if base == "fast" else "strict24")] = (
                                    lambda tt, lo=lo, hi_=hi_: np.where(np.asarray(tt) < st.cutoff + STRICT_S,
                                                                         np.maximum(lo(tt), hi_(tt)), lo(tt)))
                        for tg in TARGETS:
                            for arm in ARMS:
                                key = f"{name}_{tg:g}_{arm}"
                                f = fn.get((tg, arm)) if usable else None
                                if f is None:
                                    rec[f"warned_{key}"], rec[f"fa_{key}"], rec[f"hours_{key}"] = float("nan"), 0, 0.0
                                    continue
                                wa = evaluate_all_varying(seqs_for(pre_rel, s_pre, t, y, tl, [st.next_onset]), f,
                                                          step_s, **kw)
                                fa_a = (evaluate_all_varying(seqs_for(inter_rel, s_int, t, y, tl), f, step_s, **kw)
                                        if len(inter_rel) else None)
                                rec[f"warned_{key}"] = min(wa.n_predicted, 1)
                                rec[f"fa_{key}"] = fa_a.n_false if fa_a else 0
                                rec[f"hours_{key}"] = fa_a.far_hours if fa_a else 0.0
                rows_out.append(rec)

    # ---------------------------------------------------------------- summary, report and figure
    fields = sorted({k for r in rows_out for k in r}, key=lambda k: (k not in ("subject", "k"), k))
    if args.summarize_only:
        fields = None
    if fields is not None:
        with open(args.out / f"learning_curve{args.tag}.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(rows_out)
    bins = ["0", "1", "2", "3", "4", "5+"]
    by_bin = defaultdict(list)
    for r in rows_out:
        by_bin[bin_of(int(r["k"]))].append(r)
    lines = ["# Continuous personalization, simulated forward in time (SeizeIT2 development patients)", "",
             f"Generated {datetime.now().isoformat(timespec='seconds')} · seed {args.seed} · "
             f"{len({r['subject'] for r in rows_out})} patients, {len(rows_out)} steps · "
             "docs/evaluation_methods.md v1.19. Each step is scored only on the time after it was trained.", "",
             "| Seizures learned | Steps | AUROC, learning device | AUROC, general + baseline only | "
             "Warned (≤ 5 / 24 h), learning device | False alarms / 24 h | Warned, general only | False alarms / 24 h |",
             "|---|---|---|---|---|---|---|---|"]
    curve = {m: [] for m in MODELS}
    for b in bins:
        rs = by_bin.get(b, [])
        if not rs:
            continue
        cells = []
        for m in MODELS:
            vals = [num(r, f"auroc_{m}") for r in rs if not np.isnan(num(r, f"auroc_{m}"))]
            mean = float(np.mean(vals)) if vals else float("nan")
            ci = bootstrap_ci(vals, 1000, 0) if vals else (float("nan"), float("nan"))
            curve[m].append((b, mean, ci, len(vals)))
            cells.append(f"{mean:.3f} ({ci[0]:.2f}–{ci[1]:.2f}, n={len(vals)})")
        alarm_cells = []
        for m in MODELS:
            ws = [num(r, f"warned_{m}_5") for r in rs if not np.isnan(num(r, f"warned_{m}_5"))]
            fa = sum(num(r, f"fa_{m}_5", 0.0) for r in rs)
            hrs = sum(num(r, f"hours_{m}_5", 0.0) for r in rs)
            alarm_cells += [f"{np.mean(ws):.2f} (n={len(ws)})" if ws else "–",
                            f"{24 * fa / hrs:.2f}" if hrs else "–"]
        ip, ig = MODELS.index("personal"), MODELS.index("general")      # this table: blend vs never learns
        lines.append(f"| {b} | {len(rs)} | {cells[ip]} | {cells[ig]} | {alarm_cells[2 * ip]} | {alarm_cells[2 * ip + 1]} "
                     f"| {alarm_cells[2 * ig]} | {alarm_cells[2 * ig + 1]} |")
    if args.adaptive:
        lines += ["", "## Fixed and adaptive thresholds, over all steps after at least one learned seizure", "",
                  "| Model | Threshold | Target | Seizures warned | False alarms / 24 h | Chance | p |",
                  "|---|---|---|---|---|---|---|"]
        after = [r for r in rows_out if int(r["k"]) >= 1]
        for m in MODELS:
            for mode in ("", "_adaptive"):
                for tg in TARGETS:
                    key = f"{m}_{tg:g}{mode}"
                    ws = [num(r, f"warned_{key}") for r in after if not np.isnan(num(r, f"warned_{key}"))]
                    fa = sum(num(r, f"fa_{key}", 0.0) for r in after)
                    hrs = sum(num(r, f"hours_{key}", 0.0) for r in after)
                    far = 24 * fa / hrs if hrs else float("nan")
                    c, pv = chance_p_value(int(sum(ws)), len(ws), far, rules.preictal_start_s - rules.sph_s)
                    lines.append(f"| {DISPLAY[m]} | "
                                 f"{'adaptive' if mode else 'fixed'} | ≤ {tg:g} | {int(sum(ws))}/{len(ws)} "
                                 f"({np.mean(ws):.2f}) | {far:.2f} | {c:.3f} | {pv:.3g} |")
    if args.arms:
        lines += ["", "## v1.22 arms, over all steps after at least one learned seizure", "",
                  "Same models; only the threshold schedule differs. `strict24` and `fast_strict24` exist for the "
                  "≤ 5 setting only (they use the stricter of the ≤ 5 and ≤ 1 thresholds in the first 24 h after "
                  "each retraining).", "",
                  "| Model | Arm | Target | Seizures warned | False alarms / 24 h | Chance | p |",
                  "|---|---|---|---|---|---|---|"]
        after = [r for r in rows_out if int(r["k"]) >= 1]
        for m in MODELS:
            for tg in TARGETS:
                for arm in ARMS:
                    key = f"{m}_{tg:g}_{arm}"
                    if key.replace(f"{m}_", "", 1) in ("1_strict24", "1_fast_strict24"):
                        continue
                    ws = [num(r, f"warned_{key}") for r in after if not np.isnan(num(r, f"warned_{key}"))]
                    if not ws:
                        continue
                    fa = sum(num(r, f"fa_{key}", 0.0) for r in after)
                    hrs = sum(num(r, f"hours_{key}", 0.0) for r in after)
                    far = 24 * fa / hrs if hrs else float("nan")
                    c, pv = chance_p_value(int(sum(ws)), len(ws), far, rules.preictal_start_s - rules.sph_s)
                    lines.append(f"| {DISPLAY[m]} | {arm} | ≤ {tg:g} | "
                                 f"{int(sum(ws))}/{len(ws)} ({np.mean(ws):.2f}) | {far:.2f} | {c:.3f} | {pv:.3g} |")
    if args.recipes:
        from scipy.stats import wilcoxon
        lines += ["", "## v1.23 recipes: paired AUROC against the current blend, by learning stage", "",
                  "Steps where both models were scored. Positive differences favor the recipe.", "",
                  "| Recipe | Seizures learned | Steps | Recipe AUROC | Blend AUROC | Recipe higher | Wilcoxon p |",
                  "|---|---|---|---|---|---|---|"]
        for recipe in ("personal75", "patient_only"):
            for lab, lo, hi in (("1 or more", 1, 99), ("1–2", 1, 2), ("3–4", 3, 4), ("5 or more", 5, 99)):
                pr = [(num(r, f"auroc_{recipe}"), num(r, "auroc_personal")) for r in rows_out
                      if lo <= int(r["k"]) <= hi and not np.isnan(num(r, f"auroc_{recipe}"))
                      and not np.isnan(num(r, "auroc_personal"))]
                if not pr:
                    lines.append(f"| {recipe} | {lab} | 0 | – | – | – | – |")
                    continue
                a, b = map(np.array, zip(*pr))
                pv = wilcoxon(a, b).pvalue if len(pr) >= 2 and np.any(a != b) else float("nan")
                lines.append(f"| {recipe} | {lab} | {len(pr)} | {a.mean():.3f} | {b.mean():.3f} | "
                             f"{(a > b).sum()} of {len(pr)} | {pv:.3g} |")
    (args.out / f"learning_curve{args.tag}.md").write_text("\n".join(lines) + "\n")
    if args.log_alarms:
        with open(args.out / f"alarm_log{args.tag}.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(alarm_log[0]) if alarm_log else ["subject"], lineterminator="\n")
            w.writeheader()
            w.writerows(alarm_log)
        print(f"Alarm log: {args.out / f'alarm_log{args.tag}.csv'} ({len(alarm_log)} alarms)")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    colors = {"personal": "#2b6cb0", "general": "#a0aec0", "personal75": "#805ad5", "patient_only": "#38a169"}
    for m in MODELS:
        pts = [(i, mean, ci) for i, (b, mean, ci, n) in enumerate(curve[m]) if not np.isnan(mean)]
        if not pts:
            continue
        xs, ys, cis = zip(*pts)
        ax.plot(xs, ys, marker="o", color=colors[m], lw=2.2, label=LABELS[m])
        ax.fill_between(xs, [c[0] for c in cis], [c[1] for c in cis], color=colors[m], alpha=0.15)
    ax.axhline(0.5, color="#1f2933", lw=1, ls="--")
    ax.text(0.02, 0.505, "coin flip", fontsize=9, color="#6b7785")
    ax.set_xticks(range(len(curve["personal"])))
    ax.set_xticklabels([b for b, *_ in curve["personal"]])
    ax.set_xlabel("seizures the device has learned from", fontsize=10.5)
    ax.set_ylabel("AUROC on the time that follows", fontsize=10.5)
    ax.set_title("Simulated device that keeps learning its wearer (SeizeIT2 development patients)", fontsize=11.5)
    ax.legend(fontsize=9, frameon=False, loc="lower right")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    figs = REPO / "results" / "figures"
    figs.mkdir(parents=True, exist_ok=True)
    fig.savefig(figs / f"learning_curve{args.tag}.png", dpi=170)

    print()
    print("\n".join(lines[5:]))
    print(f"\nReport: {args.out / f'learning_curve{args.tag}.md'}; figure: {figs / f'learning_curve{args.tag}.png'}  "
          f"({(time.time() - t_start) / 60:.0f} min)")


if __name__ == "__main__":
    main()

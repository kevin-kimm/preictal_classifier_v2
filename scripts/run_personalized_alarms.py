"""Alarm-level test of the personalized designs (docs/evaluation_methods.md v1.5, Section 11.2).

Same 22 patients, leave-one-seizure-out folds, buffers and seeds as the patient-specific
test. For each held-out seizure:

* the alarm threshold is chosen from the patient's training data only: the training
  interictal windows are split into 3 chunks, each scored by a model trained without
  it, and the threshold is the lowest of 1,000 candidates whose false alarm rate on
  those out-of-sample scores is at most the target;
* alarms use the D2 settings chosen on all patients (risk averaged over 36 windows,
  above threshold for 6 windows in a row, 30 min refractory period);
* the held-out seizure counts as warned if an alarm falls 5 s to 30 min before its
  onset (scored from 35 min before onset, so smoothing has 5 min to warm up), and
  every alarm on the held-out interictal chunk is a false alarm.

Variants: general (other patients only), general_personal (other patients + this
patient, half the weight), ps_eeg_ctx_clock (this patient only, with context and time
of day). Targets: at most 5 and at most 1 false alarms per 24 h.

Frozen design (evaluation methods v1.13, Section 11.5):
    --frozen      other patients + this patient (and other patients only, for comparison) with
                  feature set v2, 10 min context, the personal baseline and no time of day. Every
                  model's personal baseline comes from its own training windows only.

Usage, from the repo root with .venv active:
    python scripts/run_personalized_alarms.py                  all variants, five seeds (about 4 h)
    python scripts/run_personalized_alarms.py --frozen         the frozen design
    python scripts/run_personalized_alarms.py --seeds 0        quicker look

Outputs: results/d2/personalized_alarms.md and personalized_alarms.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.config import load_config  # noqa: E402
from preictal.data.labels import INTERICTAL, PREICTAL, LabelRules  # noqa: E402
from preictal.data.loaders import DEFAULT_CORRECTIONS  # noqa: E402
from preictal.evaluation.lopo import read_label_report  # noqa: E402
from preictal.evaluation.metrics import (  # noqa: E402
    AlarmResult, Sequence, chance_p_value, choose_threshold_bisect, evaluate_all,
)
from preictal.evaluation.patient_specific import inner_interictal_folds, patient_folds  # noqa: E402
from preictal.features.build_features import FEATURE_VERSION, FEATURE_VERSION_V2, feature_version  # noqa: E402
from preictal.features.transforms import cache_key, clock_features, context_features, timeline_has_clock  # noqa: E402
from preictal.models.model import build_model, predict_proba  # noqa: E402
from preictal.models.train import TRAIN_CLASSES, blend_weights, load_windows, sample_weights  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

VARIANTS = ("general", "general_personal", "ps_eeg_ctx_clock")
LABELS = {"general": "Other patients only, EEG + time of day",
          "general_personal": "Other patients + this patient, EEG + time of day",
          "ps_eeg_ctx_clock": "This patient only, EEG + 10 min context + time of day"}
TARGETS = (5.0, 1.0)
OTHERS_EVERY = 6
SMOOTHING, PERSISTENCE = 36, 6      # D2 alarm settings chosen on all patients
WARMUP_S = 300.0


def fit(X, y, w, seed):
    model = build_model(seed)
    model.fit(X, y, sample_weight=w)
    return model


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, nargs="+", default=None)
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS), choices=VARIANTS)
    ap.add_argument("--features", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=REPO / "results" / "d2")
    ap.add_argument("--frozen", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.frozen:
        args.variants = [v for v in args.variants if v in ("general", "general_personal")]
        LABELS.update({"general": "Other patients only (frozen design's features and baseline)",
                       "general_personal": "Frozen design: other patients + this patient"})
    if args.features is None:
        args.features = REPO / "data" / "processed" / ("features_v2" if args.frozen else "features")
    tag = "_frozen" if args.frozen else ""

    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    seeds = args.seeds if args.seeds is not None else cfg["evaluation"]["seeds"]
    step_s = cfg["windows"]["step_s"]
    datasets = tuple(cfg["training"]["datasets"])
    corrections = DEFAULT_CORRECTIONS.read_text() if DEFAULT_CORRECTIONS.exists() else ""
    version = feature_version(cfg, corrections, FEATURE_VERSION_V2 if args.frozen else FEATURE_VERSION)
    subjects = read_label_report(REPO / "results" / "d1" / "label_report.csv")
    tl_info = json.loads((args.features / "timelines.json").read_text())
    kw = dict(sph_s=rules.sph_s, horizon_s=rules.preictal_start_s,
              refractory_s=cfg["alarm"]["refractory_min"] * 60, smoothing=SMOOTHING, persistence=PERSISTENCE)
    n_cand = cfg["alarm"]["threshold_candidates"]

    print("Loading features...")
    W = load_windows(args.features, datasets, version=version, keep_per_channel=False)
    clock = clock_features(W.t_end, np.array([timeline_has_clock(k) for k in W.timelines])[W.timeline])
    X_clock = np.hstack([W.X, clock])
    X_ctx_clock = None
    if "ps_eeg_ctx_clock" in args.variants:
        cache = args.features.parent / "d2_cache" / f"train_ctx10r_{version}_{cache_key(W)}.npy"
        if cache.exists():
            ctx = np.load(cache)
        else:
            print("  computing 10 min context features (one-off, cached)...")
            ctx = context_features(W.X, W.timeline, W.t_end, 600)
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.save(cache, ctx)
        X_ctx_clock = np.hstack([W.X, ctx, clock])
    feats = {"general": X_clock, "general_personal": X_clock, "ps_eeg_ctx_clock": X_ctx_clock}

    def scale(M, ref):
        """Personal baseline: each column minus ref's median, over ref's interquartile range (floor 0.001)."""
        with np.errstate(all="ignore"):
            med = np.nanmedian(ref, axis=0)
            iqr = np.maximum(np.nanpercentile(ref, 75, axis=0) - np.nanpercentile(ref, 25, axis=0), 1e-3)
        return (M - med) / iqr

    scaled_all = None
    if args.frozen:                     # feature set v2 + 10 min context, no time of day
        cache = args.features.parent / "d2_cache" / f"train_ctx10r_{version}_{cache_key(W)}.npy"
        if cache.exists():
            ctx = np.load(cache)
        else:
            print("  computing 10 min context features (one-off, cached)...")
            ctx = context_features(W.X, W.timeline, W.t_end, 600)
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.save(cache, ctx)
        Xf = np.hstack([W.X, ctx])
        feats = {"general": Xf, "general_personal": Xf}
        scaled_all = np.empty_like(Xf)
        for code in range(len(W.subjects)):     # other patients: scaled by all their own interictal windows
            r = np.flatnonzero(W.subject == code)
            ref = r[W.y[r] == INTERICTAL]
            scaled_all[r] = scale(Xf[r], Xf[ref]) if len(ref) else Xf[r]

    patients = []
    for code, subject in enumerate(W.subjects):
        info = subjects.get(subject)
        if info is None or info.role != "train_test":
            continue
        rows = np.flatnonzero(W.subject == code)
        events = [(tl, on) for tl in np.unique(W.timeline[rows]) for on in tl_info[W.timelines[tl]]["eligible_onsets"]]
        if len(events) >= 2 and (W.y[rows] == INTERICTAL).sum() * step_s >= 3600:
            patients.append((subject, rows, events))
    pool = {s for s, i in subjects.items() if i.dataset in datasets and i.role == "train_test"}
    print(f"{len(patients)} patients; variants: {', '.join(args.variants)}")

    def seqs_for(rel, scores, t, y, tl, onsets=()):
        out = []
        order = np.lexsort((t[rel], tl[rel]))
        rel, scores = rel[order], scores[order]
        for code in np.unique(tl[rel]):
            m = tl[rel] == code
            on = np.array(onsets, float)
            out.append(Sequence("", t[rel][m], scores[m], y[rel][m], on, on))
        return out

    rows_out = []
    it = tqdm(patients, desc="patients") if tqdm else patients
    for subject, rows, events in it:
        t, y, tl = W.t_end[rows], W.y[rows], W.timeline[rows]
        folds = [(i, tr, te) for i, tr, te in patient_folds(t, y, tl, events, rules.preictal_start_s, rules.sph_s,
                                                             rules.interictal_gap_s)
                 if (y[tr] == PREICTAL).any() and (y[tr] == INTERICTAL).any()]
        others = W.rows(pool - {subject})
        others = others[np.isin(W.y[others], TRAIN_CLASSES)]
        others = others[np.round(W.t_end[others] / 5.0).astype(np.int64) % OTHERS_EVERY == 0]
        events_sorted = sorted(events)
        for seed in seeds:
            general = None
            if "general" in args.variants:
                Xo = scaled_all[others] if args.frozen else X_clock[others]
                general = fit(Xo, W.y[others], sample_weights(W.y[others], W.subject[others]), seed)
            totals = {(v, tg): AlarmResult() for v in args.variants for tg in TARGETS}
            for i, train, test in folds:
                tl_e, onset = events_sorted[i]
                pre_seq_rel = np.flatnonzero((tl == tl_e) & (t >= onset - rules.preictal_start_s - WARMUP_S)
                                             & (t <= onset - rules.sph_s))
                chunk = test[y[test] == INTERICTAL]

                def patient_X(v, ref_rel):
                    """This patient's rows; with --frozen, scaled by the interictal windows among ref_rel."""
                    M = feats[v][rows]
                    if not args.frozen:
                        return M
                    ref = ref_rel[y[ref_rel] == INTERICTAL]
                    return scale(M, M[ref])

                others_X = scaled_all[others] if args.frozen else None

                def train_model(v, rel, P):
                    rel = rel[np.isin(y[rel], TRAIN_CLASSES)]
                    if v == "general_personal":
                        Xo = others_X if args.frozen else feats[v][others]
                        wg, wp = blend_weights(W.y[others], W.subject[others], y[rel], 0.5)
                        return fit(np.vstack([Xo, P[rel]]), np.concatenate([W.y[others], y[rel]]),
                                   np.concatenate([wg, wp]), seed)
                    return fit(P[rel], y[rel], sample_weights(y[rel], np.zeros(len(rel), int)), seed)

                for v in args.variants:
                    # threshold from the training data only
                    inner_seqs = []
                    for inner_train, inner_chunk in inner_interictal_folds(t, y, tl, train):
                        P_in = patient_X(v, inner_train)
                        m = general if v == "general" else train_model(v, inner_train, P_in)
                        inner_seqs += seqs_for(inner_chunk, predict_proba(m, P_in[inner_chunk])[:, 0], t, y, tl)
                    P = patient_X(v, train)
                    model = general if v == "general" else train_model(v, train, P)
                    pre = seqs_for(pre_seq_rel, predict_proba(model, P[pre_seq_rel])[:, 0], t, y, tl, [onset])
                    inter = seqs_for(chunk, predict_proba(model, P[chunk])[:, 0], t, y, tl)
                    for tg in TARGETS:
                        thr, _ = choose_threshold_bisect(inner_seqs, tg, step_s, n_cand, **kw)
                        warned = evaluate_all(pre, thr, step_s, **kw)
                        fa = evaluate_all(inter, thr, step_s, **kw)
                        totals[(v, tg)] = totals[(v, tg)].add(AlarmResult(
                            n_events=1, n_predicted=min(warned.n_predicted, 1), n_alarms=fa.n_alarms,
                            n_false=fa.n_false, far_hours=fa.far_hours, n_windows=fa.n_windows,
                            n_warning_windows=fa.n_warning_windows, warning_times=warned.warning_times))
            for (v, tg), r in totals.items():
                if r.n_events:
                    rows_out.append({"seed": seed, "subject": subject, "variant": v, "far_target": tg,
                                     "seizures": r.n_events, "warned": r.n_predicted, "false_alarms": r.n_false,
                                     "interictal_hours": round(r.far_hours, 3), "far_per_24h": r.far_per_24h,
                                     "median_warning_min": (np.median(r.warning_times) / 60 if r.warning_times
                                                            else float("nan"))})

    with open(args.out / f"personalized_alarms{tag}.csv", "w", newline="") as fh:
        wtr = csv.DictWriter(fh, fieldnames=list(rows_out[0]), lineterminator="\n")
        wtr.writeheader()
        wtr.writerows(rows_out)

    lines = ["# Personalized designs: alarm-level test (characterization)", "",
             f"Generated {datetime.now().isoformat(timespec='seconds')} · seeds {seeds} · "
             f"{len({r['subject'] for r in rows_out})} patients · docs/evaluation_methods.md v1.5, Section 11.2. "
             "Thresholds chosen from each patient's training data only.", "",
             "| Model | False-alarm target | Seizures warned | False alarms per 24 h | Chance probability | p (vs chance) "
             "| Patients with at least one seizure warned |", "|---|---|---|---|---|---|---|"]
    printed = []
    for v in args.variants:
        for tg in TARGETS:
            sens, far, pv, cp, helped = [], [], [], [], []
            for s in seeds:
                rs = [r for r in rows_out if r["variant"] == v and r["far_target"] == tg and r["seed"] == s]
                n_ev = sum(r["seizures"] for r in rs)
                n_w = sum(r["warned"] for r in rs)
                hours = sum(r["interictal_hours"] for r in rs)
                f = 24 * sum(r["false_alarms"] for r in rs) / hours if hours else float("nan")
                c, p = chance_p_value(n_w, n_ev, f, rules.preictal_start_s - rules.sph_s)
                sens.append(n_w / n_ev if n_ev else float("nan"))
                far.append(f)
                pv.append(p)
                cp.append(c)
                helped.append(sum(r["warned"] > 0 for r in rs))
            n_pat = len({r["subject"] for r in rows_out if r["variant"] == v})
            line = (f"| {LABELS[v]} | ≤ {tg:g} | {np.mean(sens):.2f} | {np.mean(far):.2f} | {np.mean(cp):.3f} "
                    f"| {np.median(pv):.3g} (median over seeds) | {np.mean(helped):.1f} of {n_pat} |")
            lines.append(line)
            printed.append(f"{LABELS[v]:55s} target ≤{tg:g}/24h: warned {np.mean(sens):.2f}, "
                           f"FAR {np.mean(far):.2f}/24h, chance {np.mean(cp):.2f}, median p {np.median(pv):.3g}")
    lines += ["", "## Per patient (target ≤ 5 per 24 h, mean over seeds)", "",
              "| Patient | Seizures | " + " | ".join(f"{LABELS[v]}: warned / FAR" for v in args.variants) + " |",
              "|---|---|" + "---|" * len(args.variants)]
    per = defaultdict(lambda: defaultdict(list))
    for r in rows_out:
        if r["far_target"] == 5.0:
            per[r["subject"]][r["variant"]].append(r)
    for s in sorted(per):
        cells = []
        for v in args.variants:
            rs = per[s][v]
            cells.append(f"{np.mean([r['warned'] for r in rs]):.1f}/{rs[0]['seizures']} · "
                         f"{np.mean([r['far_per_24h'] for r in rs]):.1f}")
        lines.append(f"| {s} | {per[s][args.variants[0]][0]['seizures']} | " + " | ".join(cells) + " |")
    (args.out / f"personalized_alarms{tag}.md").write_text("\n".join(lines) + "\n")

    print()
    for x in printed:
        print(x)
    print(f"Report: {args.out / f'personalized_alarms{tag}.md'}")


if __name__ == "__main__":
    main()

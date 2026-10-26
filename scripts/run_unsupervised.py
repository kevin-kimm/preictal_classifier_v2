"""D2 improvement round: can EEG show an approaching seizure with no seizure labels?
(docs/evaluation_methods.md v1.25, Section 14.6; the instructor's comment, p. 2.) A characterization.

For each patient, the same leave-one-seizure-out folds and buffers as the frozen design. Instead of a
classifier, an anomaly detector (isolation forest) learns what this patient's EEG usually looks like and
scores how unusual each test window is. Nothing tells it which windows came before seizures:

    normal_only   learns from the fold's training windows that are at least 4 h from any seizure
                  (this needs to know when seizures happened, but not what comes before them)
    label_free    learns from every training window of the patient, whatever its label

Features are the frozen design's (feature set v2 + 10 min context), scaled by the fold's own interictal
training windows (the personal baseline). Seeds 0 to 4 set the isolation forest's randomness.

Reported:
    * AUROC of the anomaly score, preictal vs interictal, on the frozen test windows (directly comparable
      with the frozen design's supervised AUROC);
    * the time course: the anomaly score in 5 min bins over the 4 h before each held-out seizure (never
      trained on: it lies inside the 4 h buffer), as a z-score against the fold's training interictal
      scores, compared with the same 4 h aligned to the end of an interictal stretch (no seizure).

Usage, from the repo root with .venv active:
    python scripts/run_unsupervised.py                       CHB-MIT and Siena, seeds 0-4
    python scripts/run_unsupervised.py --dataset seizeit2    SeizeIT2 development patients

Outputs: results/d2_plus/<dataset>/unsupervised.md, unsupervised.csv, unsupervised_timecourse.csv and
results/d2_plus/<dataset>/unsupervised_timecourse.png
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.config import load_config  # noqa: E402
from preictal.data.labels import INTERICTAL, PREICTAL, LabelRules  # noqa: E402
from preictal.data.loaders import DEFAULT_CORRECTIONS  # noqa: E402
from preictal.evaluation.lopo import read_label_report  # noqa: E402
from preictal.evaluation.metrics import bootstrap_ci  # noqa: E402
from preictal.evaluation.patient_specific import patient_folds  # noqa: E402
from preictal.features.build_features import FEATURE_VERSION_V2, feature_version  # noqa: E402
from preictal.features.transforms import cache_key, context_features  # noqa: E402
from preictal.models.train import load_windows  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

VARIANTS = ("normal_only", "label_free")
LABELS = {"normal_only": "Learns normal EEG only (seizure times known, nothing about what precedes them)",
          "label_free": "Learns from all EEG (no labels at all)"}
LOOKBACK_S = 4 * 3600.0
BIN_S = 300.0
FIT_EVERY = 6            # fit on windows 30 s apart (overlapping windows add little)


def auroc(y, s):
    y = np.asarray(y, bool)
    return float(roc_auc_score(y, s)) if y.any() and (~y).any() else float("nan")


def scale(M, ref):
    with np.errstate(all="ignore"):
        med = np.nanmedian(ref, axis=0)
        iqr = np.maximum(np.nanpercentile(ref, 75, axis=0) - np.nanpercentile(ref, 25, axis=0), 1e-3)
    return (M - med) / iqr


def clean(X):
    """Isolation forests can't take missing values: missing features (absent channels) become 0, the
    personal-baseline median."""
    X = np.array(X, dtype=np.float32)
    X[~np.isfinite(X)] = 0.0
    return X


def main():
    warnings.filterwarnings("ignore", category=RuntimeWarning)     # empty bins in the time course are expected
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", choices=["chbmit_siena", "seizeit2"], default="chbmit_siena")
    ap.add_argument("--seeds", type=int, nargs="+", default=None)
    ap.add_argument("--patients", nargs="+", default=None)
    args = ap.parse_args()
    sz2 = args.dataset == "seizeit2"
    out = REPO / "results" / "d2_plus" / args.dataset
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    seeds = args.seeds if args.seeds is not None else cfg["evaluation"]["seeds"]
    step_s = cfg["windows"]["step_s"]
    features = REPO / "data" / "processed" / ("features_seizeit2" if sz2 else "features_v2")
    datasets = ("seizeit2",) if sz2 else tuple(cfg["training"]["datasets"])
    corrections = DEFAULT_CORRECTIONS.read_text() if DEFAULT_CORRECTIONS.exists() else ""
    version = feature_version(cfg, corrections, FEATURE_VERSION_V2)
    subjects = read_label_report(REPO / "results" / "d1" / "label_report.csv")
    test_subjects = None
    if sz2:
        from preictal.data.seizeit2 import FEATURE_CODE, VERSION_TEXT, cohort
        version = feature_version(cfg, VERSION_TEXT, FEATURE_CODE)
        subjects, test_subjects, sz_pool = cohort(REPO, "development")
    tl_info = json.loads((features / "timelines.json").read_text())

    print("Loading features...")
    W = load_windows(features, datasets, subjects=test_subjects if sz2 else None, version=version,
                     keep_per_channel=False)      # SeizeIT2: development patients only
    cache = features.parent / "d2_cache" / f"train_ctx10r_{version}_{cache_key(W)}.npy"
    if cache.exists():
        ctx = np.load(cache)
    else:
        print("  computing 10 min context features (one-off, cached)...")
        ctx = context_features(W.X, W.timeline, W.t_end, 600)
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.save(cache, ctx)
    Xf = np.hstack([W.X, ctx])
    y_all = W.y

    patients = []
    for code, subject in enumerate(W.subjects):
        info = subjects.get(subject)
        if info is None or info.role != "train_test" or (test_subjects is not None and subject not in test_subjects):
            continue
        if args.patients and subject not in args.patients and subject.split(":")[-1] not in args.patients:
            continue
        rows = np.flatnonzero(W.subject == code)
        events = [(tl, on) for tl in np.unique(W.timeline[rows]) for on in tl_info[W.timelines[tl]]["eligible_onsets"]]
        if len(events) >= 2 and (y_all[rows] == INTERICTAL).sum() * step_s >= 3600:
            patients.append((subject, rows, events))
    print(f"{len(patients)} patients; seeds {seeds}")

    n_bins = int(LOOKBACK_S / BIN_S)
    rows_out = []
    course = {v: {"seizure": defaultdict(list), "control": defaultdict(list)} for v in VARIANTS}
    it = tqdm(patients, desc="patients") if tqdm else patients
    for subject, rows, events in it:
        t, y, tl = W.t_end[rows], y_all[rows], W.timeline[rows]
        M = Xf[rows]
        events_sorted = sorted(events)
        folds = [(i, tr, te) for i, tr, te in patient_folds(t, y, tl, events, rules.preictal_start_s, rules.sph_s,
                                                             rules.interictal_gap_s)
                 if (y[tr] == PREICTAL).any() and (y[tr] == INTERICTAL).any()]
        everything = np.full(len(y), INTERICTAL, dtype=y.dtype)
        free = {i: tr for i, tr, _ in patient_folds(t, y, tl, events, rules.preictal_start_s, rules.sph_s,
                                                    rules.interictal_gap_s, train_labels=everything)}
        if not folds:
            continue
        sub_course = {v: {"seizure": [], "control": []} for v in VARIANTS}
        for seed in seeds:
            preds, labels = defaultdict(list), []
            for i, train, test in folds:
                tl_e, onset = events_sorted[i]
                ref = train[y[train] == INTERICTAL]
                P = clean(scale(M, M[ref]))
                fit_rows = {"normal_only": ref, "label_free": free[i]}
                lead = np.flatnonzero((tl == tl_e) & (t >= onset - LOOKBACK_S) & (t <= onset - rules.sph_s))
                chunk = test[y[test] == INTERICTAL]
                labels.append(y[test])
                for v in VARIANTS:
                    fr = fit_rows[v]
                    fr = fr[np.round(t[fr] / 5.0).astype(np.int64) % FIT_EVERY == 0]
                    model = IsolationForest(n_estimators=200, max_samples=min(2048, len(fr)), random_state=seed)
                    model.fit(P[fr])
                    preds[v].append(-model.score_samples(P[test]))
                    if seed != seeds[0]:
                        continue
                    base = -model.score_samples(P[ref])
                    mu, sd = float(np.mean(base)), float(np.std(base)) or 1.0
                    z_lead = (-model.score_samples(P[lead]) - mu) / sd if len(lead) else np.array([])
                    b = np.floor((onset - t[lead]) / BIN_S).astype(int)
                    sub_course[v]["seizure"].append(_bin(z_lead, b, n_bins))
                    if len(chunk):
                        c_end = t[chunk].max()
                        same = chunk[tl[chunk] == tl[chunk][np.argmax(t[chunk])]]
                        zc = (-model.score_samples(P[same]) - mu) / sd
                        bc = np.floor((c_end + rules.sph_s - t[same]) / BIN_S).astype(int)
                        sub_course[v]["control"].append(_bin(zc, bc, n_bins))
            lab = np.concatenate(labels)
            pi = np.isin(lab, (PREICTAL, INTERICTAL))
            rec = {"seed": seed, "subject": subject, "seizures": len(events), "folds": len(folds)}
            for v in VARIANTS:
                rec[v] = auroc(lab[pi] == PREICTAL, np.concatenate(preds[v])[pi])
            rows_out.append(rec)
        for v in VARIANTS:
            for kind in ("seizure", "control"):
                if sub_course[v][kind]:
                    course[v][kind][subject] = np.nanmean(np.vstack(sub_course[v][kind]), axis=0)

    write(out, rows_out, course, n_bins, args.dataset, seeds)


def _bin(z, b, n_bins):
    v = np.full(n_bins, np.nan)
    for k in range(n_bins):
        m = b == k
        if m.any():
            v[k] = float(np.mean(z[m]))
    return v


def write(out, rows_out, course, n_bins, dataset, seeds):
    if not rows_out:
        print("No patients scored.")
        return
    with open(out / "unsupervised.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows_out)
    per = {v: defaultdict(list) for v in VARIANTS}
    for r in rows_out:
        for v in VARIANTS:
            per[v][r["subject"]].append(r[v])
    frozen = {}
    prog = out / "progress.jsonl"
    if prog.exists():
        fz = defaultdict(list)
        for line in prog.read_text().splitlines():
            r = json.loads(line)
            if r["arm"] == "frozen" and not r.get("alarms"):
                fz[r["subject"]].append(r["auroc"])
        frozen = {s: float(np.mean(v)) for s, v in fz.items()}
    lines = ["# Unsupervised test: does EEG change before seizures, with no labels?", "",
             f"Generated {datetime.now().isoformat(timespec='seconds')} · {dataset} · seeds {seeds} · "
             "docs/evaluation_methods.md v1.25, Section 14.6. Same patients, folds and test windows as the frozen "
             "design.", "",
             "| Model | Patients | Mean AUROC | 95% CI | Patients above 0.5 |", "|---|---|---|---|---|"]
    for v in VARIANTS:
        vals = [float(np.nanmean(x)) for x in per[v].values()]
        ci = bootstrap_ci(vals, 1000, 0)
        lines.append(f"| {LABELS[v]} | {len(vals)} | {np.nanmean(vals):.3f} | {ci[0]:.3f}–{ci[1]:.3f} "
                     f"| {sum(x > 0.5 for x in vals)} of {len(vals)} |")
    if frozen:
        common = sorted(set(frozen) & set(per["normal_only"]))
        lines.append(f"| Frozen design (supervised, same patients; from progress.jsonl) | {len(common)} "
                     f"| {np.mean([frozen[s] for s in common]):.3f} | | |")
    lines += ["", "## Time course over the 4 h before seizures (seed " + str(seeds[0]) + ")", "",
              "Mean anomaly z-score per 5 min bin (per patient first, then across patients), against the same "
              "4 h at the end of the held-out interictal stretch (shorter when that stretch is shorter). Both are "
              "windows the model never trained on, so compare the two curves with each other rather than with zero: "
              "unseen EEG always looks a little unusual. A rise towards the seizure that the control doesn't show "
              "would mean the EEG becomes unusual before seizures without anyone labelling it. Other seizures in the "
              "4 h before a seizure also show up as peaks.", "",
              "| Minutes before | " + " | ".join(f"{LABELS[v].split(' (')[0]}: before seizures" for v in VARIANTS)
              + " | " + " | ".join(f"{LABELS[v].split(' (')[0]}: control" for v in VARIANTS) + " |",
              "|---|" + "---|" * (2 * len(VARIANTS))]
    mean_course = {}
    for v in VARIANTS:
        for kind in ("seizure", "control"):
            arr = np.vstack(list(course[v][kind].values())) if course[v][kind] else np.full((1, n_bins), np.nan)
            mean_course[(v, kind)] = arr
    csv_rows = []
    for k in range(n_bins - 1, -1, -1):
        lo = k * BIN_S / 60
        cells = []
        row = {"minutes_before": f"{lo + 5:.0f}-{lo:.0f}"}
        for kind in ("seizure", "control"):
            for v in VARIANTS:
                m = float(np.nanmean(mean_course[(v, kind)][:, k])) if np.isfinite(mean_course[(v, kind)][:, k]).any() else float("nan")
                cells.append(m)
                row[f"{v}_{kind}"] = m
        csv_rows.append(row)
        if k % 3 == 0 or k < 6:
            lines.append(f"| {lo + 5:.0f}–{lo:.0f} | " + " | ".join(f"{c:+.2f}" for c in cells) + " |")
    with open(out / "unsupervised_timecourse.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(csv_rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(csv_rows)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, len(VARIANTS), figsize=(11, 3.8), sharey=True)
        x = -(np.arange(n_bins) + 0.5) * BIN_S / 60
        for ax, v in zip(np.atleast_1d(axes), VARIANTS):
            for kind, color, name in (("seizure", "#c0392b", "before seizures"), ("control", "#7f8c8d", "control")):
                arr = mean_course[(v, kind)]
                with np.errstate(all="ignore"):
                    m = np.nanmean(arr, axis=0)
                    se = np.nanstd(arr, axis=0) / np.sqrt(np.maximum(np.sum(np.isfinite(arr), axis=0), 1))
                ax.plot(x, m, color=color, label=f"{name} ({arr.shape[0]} patients)")
                ax.fill_between(x, m - 1.96 * se, m + 1.96 * se, color=color, alpha=0.15, linewidth=0)
            ax.axvspan(-30, 0, color="#f1c40f", alpha=0.12, label="preictal period (30 min)")
            ax.axhline(0, color="black", linewidth=0.6)
            ax.set_title(LABELS[v].split(" (")[0], fontsize=10)
            ax.set_xlabel("minutes before seizure onset (control: before the end of normal EEG)")
        np.atleast_1d(axes)[0].set_ylabel("anomaly score (z vs normal EEG)")
        np.atleast_1d(axes)[0].legend(fontsize=8, loc="upper left")
        fig.tight_layout()
        fig.savefig(out / "unsupervised_timecourse.png", dpi=150)
        lines += ["", f"Figure: `results/d2_plus/{dataset}/unsupervised_timecourse.png`"]
    except Exception as e:      # the table is the result; the figure is a convenience
        lines += ["", f"(figure not drawn: {e})"]
    (out / "unsupervised.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nReport: {out / 'unsupervised.md'}")


if __name__ == "__main__":
    main()

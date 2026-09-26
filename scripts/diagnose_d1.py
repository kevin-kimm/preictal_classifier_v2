"""Diagnostics for the D1 baseline. Not a verification test: nothing here changes the D1 model.

Re-runs the D1 leave-one-patient-out procedure for one seed and reports three things
that help separate "bug" from "hard problem":

1. Seizure detection. How well the model's ictal probability separates ictal from
   interictal windows (AUROC), for all ictal windows and for windows lying entirely
   inside a seizure. Windows are labeled by their end time, so an "ictal" window can
   contain up to 30 s of EEG from before the seizure started.
2. Calibration across patients. The median preictal risk on each test patient's
   interictal windows. Large differences between patients mean one threshold can't
   suit everyone, and point to per-patient normalization (a D2 experiment).
3. Time of day. A model that sees only the clock time (no EEG), trained and tested the
   same way. If it scores close to the EEG model, the EEG model may be picking up
   sleep/wake or daily rhythms rather than anything specific to seizures.

Usage, from the repo root with .venv active:
    python scripts/diagnose_d1.py            seed 0
Writes results/d1/diagnostics_d1.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.config import load_config  # noqa: E402
from preictal.data.labels import ICTAL, INTERICTAL, PREICTAL  # noqa: E402
from preictal.data.loaders import DEFAULT_CORRECTIONS  # noqa: E402
from preictal.evaluation.lopo import make_folds, read_label_report  # noqa: E402
from preictal.features.build_features import feature_version  # noqa: E402
from preictal.models.model import predict_proba  # noqa: E402
from preictal.models.train import fit, load_windows  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


def auroc(y, s):
    y = np.asarray(y, bool)
    return float(roc_auc_score(y, s)) if y.any() and (~y).any() else float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--features", type=Path, default=REPO / "data" / "processed" / "features")
    ap.add_argument("--out", type=Path, default=REPO / "results" / "d1")
    args = ap.parse_args()

    cfg = load_config()
    ev = cfg["evaluation"]
    length_s = cfg["windows"]["length_s"]
    datasets = tuple(cfg["training"]["datasets"])
    corrections = DEFAULT_CORRECTIONS.read_text() if DEFAULT_CORRECTIONS.exists() else ""
    subjects = read_label_report(args.out / "label_report.csv")
    tl_info = json.loads((args.features / "timelines.json").read_text())
    W = load_windows(args.features, datasets, version=feature_version(cfg, corrections))

    # window start at or after the nearest preceding seizure onset -> entirely inside the seizure
    inside = np.zeros(len(W.y), dtype=bool)
    ictal_rows = np.flatnonzero(W.y == ICTAL)
    for code in np.unique(W.timeline[ictal_rows]):
        onsets = np.sort(np.array(tl_info[W.timelines[code]]["onsets"], dtype=float))
        rows = ictal_rows[W.timeline[ictal_rows] == code]
        t = W.t_end[rows]
        k = np.searchsorted(onsets, t, side="right") - 1
        ok = k >= 0
        inside[rows[ok]] = t[ok] - length_s >= onsets[k[ok]]
    hour = (W.t_end % 86400) / 3600
    clock = np.column_stack([np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)])

    folds = make_folds(subjects, datasets, args.seed, ev["inner_validation_fraction"], ev["inner_validation_min_patients"])
    rows_out, all_y, all_ictal_p, all_inside = [], [], [], []
    it = tqdm(folds, desc="diagnostics") if tqdm else folds
    for fold in it:
        r_train, r_test = W.rows(set(fold.train)), W.rows({fold.test})
        if len(r_test) == 0:
            continue
        model = fit(W.X[r_train], W.y[r_train], W.subject[r_train], args.seed)
        p = predict_proba(model, W.X[r_test])
        y = W.y[r_test]
        pi = np.isin(y, (PREICTAL, INTERICTAL))
        ii = np.isin(y, (ICTAL, INTERICTAL))
        ii_in = ii & ((y == INTERICTAL) | inside[r_test])
        tr = r_train[np.isin(W.y[r_train], (PREICTAL, INTERICTAL))]
        clf = LogisticRegression().fit(clock[tr], W.y[tr] == PREICTAL)
        clock_auc = auroc(y[pi] == PREICTAL, clf.predict_proba(clock[r_test][pi])[:, 1])
        rows_out.append({
            "subject": fold.test,
            "eeg_auroc": auroc(y[pi] == PREICTAL, p[pi, 0]),
            "clock_auroc": clock_auc,
            "ictal_auroc_all": auroc(y[ii] == ICTAL, p[ii, 1]),
            "ictal_auroc_inside": auroc(y[ii_in] == ICTAL, p[ii_in, 1]),
            "n_ictal": int((y == ICTAL).sum()), "n_ictal_inside": int(inside[r_test].sum()),
            "median_interictal_risk": float(np.median(p[y == INTERICTAL, 0])) if (y == INTERICTAL).any() else float("nan"),
            "median_preictal_risk": float(np.median(p[y == PREICTAL, 0])) if (y == PREICTAL).any() else float("nan"),
        })
        all_y.append(y[ii]); all_ictal_p.append(p[ii, 1]); all_inside.append(inside[r_test][ii])

    y_ii, p_ii, in_ii = np.concatenate(all_y), np.concatenate(all_ictal_p), np.concatenate(all_inside)
    pooled_all = auroc(y_ii == ICTAL, p_ii)
    keep = (y_ii == INTERICTAL) | in_ii
    pooled_inside = auroc(y_ii[keep] == ICTAL, p_ii[keep])
    m = {k: float(np.nanmean([r[k] for r in rows_out]))
         for k in ("eeg_auroc", "clock_auroc", "ictal_auroc_all", "ictal_auroc_inside")}
    spread = [r["median_interictal_risk"] for r in rows_out if not np.isnan(r["median_interictal_risk"])]

    lines = [
        "# D1 diagnostics (not a verification test)", "",
        f"Generated {datetime.now().isoformat(timespec='seconds')} · seed {args.seed} · same folds and model as "
        "the D1 run. Nothing here changes the D1 model.", "",
        "## Summary (mean over test patients)", "",
        "| Check | Value |", "|---|---|",
        f"| Preictal vs interictal, EEG model (AUROC) | {m['eeg_auroc']:.3f} |",
        f"| Preictal vs interictal, clock time only (AUROC) | {m['clock_auroc']:.3f} |",
        f"| Seizure detection, all ictal windows (AUROC of ictal probability) | {m['ictal_auroc_all']:.3f} "
        f"(pooled {pooled_all:.3f}) |",
        f"| Seizure detection, windows entirely inside a seizure | {m['ictal_auroc_inside']:.3f} "
        f"(pooled {pooled_inside:.3f}) |",
        f"| Median preictal risk on interictal windows, across patients | min {min(spread):.3f}, "
        f"median {np.median(spread):.3f}, max {max(spread):.3f} |", "",
        "## Per test patient", "",
        "| Patient | EEG AUROC | Clock AUROC | Seizure detection (all / inside) | Ictal windows (inside) "
        "| Median risk: interictal / preictal |",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted(rows_out, key=lambda r: r["eeg_auroc"]):
        lines.append(f"| {r['subject']} | {r['eeg_auroc']:.3f} | {r['clock_auroc']:.3f} "
                     f"| {r['ictal_auroc_all']:.3f} / {r['ictal_auroc_inside']:.3f} "
                     f"| {r['n_ictal']} ({r['n_ictal_inside']}) "
                     f"| {r['median_interictal_risk']:.3f} / {r['median_preictal_risk']:.3f} |")
    (args.out / "diagnostics_d1.md").write_text("\n".join(lines) + "\n")

    print()
    print(f"Preictal vs interictal AUROC:  EEG model {m['eeg_auroc']:.3f}   clock time only {m['clock_auroc']:.3f}")
    print(f"Seizure detection AUROC:       all ictal windows {m['ictal_auroc_all']:.3f} (pooled {pooled_all:.3f}),"
          f" entirely inside a seizure {m['ictal_auroc_inside']:.3f} (pooled {pooled_inside:.3f})")
    print(f"Median risk on interictal windows across patients: min {min(spread):.3f}, "
          f"median {np.median(spread):.3f}, max {max(spread):.3f}")
    print(f"Report: {args.out / 'diagnostics_d1.md'}")


if __name__ == "__main__":
    main()

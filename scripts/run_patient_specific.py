"""Patient-specific test (docs/evaluation_methods.md v1.3, Section 11). A characterization, alongside
the cross-patient results; it doesn't replace them.

For each patient with at least two eligible seizures and at least 1 h of interictal
EEG: leave one seizure out at a time, train on the rest of that patient's data
(src/preictal/evaluation/patient_specific.py), and score the held-out seizure's
preictal windows against a held-out chunk of interictal windows. The D1 model and
features are used unchanged. A patient-specific clock-only model is trained on
exactly the same windows, because time of day can separate the classes on its own.

Usage, from the repo root with .venv active:
    python scripts/run_patient_specific.py            all five seeds (about 15-30 min)

Outputs: results/d2/patient_specific.md and patient_specific.csv
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
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.config import load_config  # noqa: E402
from preictal.data.labels import INTERICTAL, PREICTAL, LabelRules  # noqa: E402
from preictal.data.loaders import DEFAULT_CORRECTIONS  # noqa: E402
from preictal.evaluation.lopo import read_label_report  # noqa: E402
from preictal.evaluation.metrics import bootstrap_ci  # noqa: E402
from preictal.evaluation.patient_specific import patient_folds  # noqa: E402
from preictal.features.build_features import feature_version  # noqa: E402
from preictal.features.transforms import clock_features, timeline_has_clock  # noqa: E402
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
    ap.add_argument("--seeds", type=int, nargs="+", default=None)
    ap.add_argument("--features", type=Path, default=REPO / "data" / "processed" / "features")
    ap.add_argument("--out", type=Path, default=REPO / "results" / "d2")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    seeds = args.seeds if args.seeds is not None else cfg["evaluation"]["seeds"]
    step_s = cfg["windows"]["step_s"]
    corrections = DEFAULT_CORRECTIONS.read_text() if DEFAULT_CORRECTIONS.exists() else ""
    subjects = read_label_report(REPO / "results" / "d1" / "label_report.csv")
    tl_info = json.loads((args.features / "timelines.json").read_text())
    W = load_windows(args.features, tuple(cfg["training"]["datasets"]),
                     version=feature_version(cfg, corrections), keep_per_channel=False)
    clock = clock_features(W.t_end, np.array([timeline_has_clock(k) for k in W.timelines])[W.timeline])

    # eligible patients: at least two eligible seizures and at least 1 h of interictal windows
    patients = []
    for code, subject in enumerate(W.subjects):
        info = subjects.get(subject)
        if info is None or info.role != "train_test":
            continue
        rows = np.flatnonzero(W.subject == code)
        events = [(tl, on) for tl in np.unique(W.timeline[rows])
                  for on in tl_info[W.timelines[tl]]["eligible_onsets"]]
        if len(events) >= 2 and (W.y[rows] == INTERICTAL).sum() * step_s >= 3600:
            patients.append((subject, rows, events))
    print(f"{len(patients)} patients with at least two eligible seizures and 1 h of interictal EEG")

    rows_out = []
    it = tqdm(patients, desc="patients") if tqdm else patients
    for subject, rows, events in it:
        t, y, tl = W.t_end[rows], W.y[rows], W.timeline[rows]
        for seed in seeds:
            scores, labels, clock_scores, n_folds = [], [], [], 0
            for i, train, test in patient_folds(t, y, tl, events, rules.preictal_start_s, rules.sph_s,
                                                rules.interictal_gap_s):
                if not (y[train] == PREICTAL).any() or not (y[train] == INTERICTAL).any():
                    continue
                n_folds += 1
                model = fit(W.X[rows][train], y[train], W.subject[rows][train], seed)
                scores.append(predict_proba(model, W.X[rows][test])[:, 0])
                labels.append(y[test])
                ck = clock[rows]
                tr = train[~np.isnan(ck[train, 0]) & np.isin(y[train], (PREICTAL, INTERICTAL))]
                te_ok = ~np.isnan(ck[test, 0])
                cs = np.full(len(test), np.nan)
                if len(tr) and len(np.unique(y[tr])) == 2 and te_ok.any():
                    lr = LogisticRegression().fit(ck[tr], y[tr] == PREICTAL)
                    cs[te_ok] = lr.predict_proba(ck[test][te_ok])[:, 1]
                clock_scores.append(cs)
            if not n_folds:
                continue
            s, lab, cs = np.concatenate(scores), np.concatenate(labels), np.concatenate(clock_scores)
            pi = np.isin(lab, (PREICTAL, INTERICTAL))
            ok = pi & ~np.isnan(cs)
            rows_out.append({"seed": seed, "subject": subject, "dataset": subjects[subject].dataset,
                             "seizures": len(events), "folds_scored": n_folds,
                             "auroc": auroc(lab[pi] == PREICTAL, s[pi]),
                             "clock_only_auroc": auroc(lab[ok] == PREICTAL, cs[ok])})

    # compare with the cross-patient results for the same patients
    cross = {"D1": defaultdict(list), "D2": defaultdict(list)}
    for name, path in (("D1", REPO / "results" / "d1" / "lopo_metrics.csv"), ("D2", args.out / "d2_metrics.csv")):
        if path.exists():
            for r in csv.DictReader(open(path)):
                cross[name][r["subject"]].append(float(r["auroc"]))

    by_subject = defaultdict(list)
    for r in rows_out:
        by_subject[r["subject"]].append(r)
    summary = {k: {"ps": float(np.nanmean([r["auroc"] for r in v])),
                   "clock": float(np.nanmean([r["clock_only_auroc"] for r in v])),
                   "d1": float(np.mean(cross["D1"][k])) if cross["D1"][k] else float("nan"),
                   "d2": float(np.mean(cross["D2"][k])) if cross["D2"][k] else float("nan"),
                   "seizures": v[0]["seizures"], "dataset": v[0]["dataset"]} for k, v in by_subject.items()}
    ps_mean = float(np.nanmean([v["ps"] for v in summary.values()]))
    ps_ci = bootstrap_ci([v["ps"] for v in summary.values()], 1000, 0)
    clock_mean = float(np.nanmean([v["clock"] for v in summary.values()]))
    d1_same = float(np.nanmean([v["d1"] for v in summary.values()]))
    d2_same = float(np.nanmean([v["d2"] for v in summary.values()]))
    above_clock = sum(v["ps"] > v["clock"] for v in summary.values() if not np.isnan(v["clock"]))

    with open(args.out / "patient_specific.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows_out)
    lines = [
        "# Patient-specific test (characterization)", "",
        f"Generated {datetime.now().isoformat(timespec='seconds')} · seeds {seeds} · D1 model and features, "
        "leave one seizure out within each patient (docs/evaluation_methods.md v1.3, Section 11).", "",
        "| Result | Value |", "|---|---|",
        f"| Patients | {len(summary)} |",
        f"| Mean patient-specific AUROC | {ps_mean:.3f} (95% CI {ps_ci[0]:.3f}–{ps_ci[1]:.3f}) |",
        f"| Patient-specific clock-only AUROC | {clock_mean:.3f} |",
        f"| Patients where the EEG model beats their clock-only model | {above_clock} of "
        f"{sum(not np.isnan(v['clock']) for v in summary.values())} |",
        f"| Same patients, cross-patient D1 AUROC | {d1_same:.3f} |",
        f"| Same patients, cross-patient D2 AUROC | {d2_same:.3f} |", "",
        "| Patient | Dataset | Seizures | Patient-specific | Clock only | Cross-patient D1 | Cross-patient D2 |",
        "|---|---|---|---|---|---|---|",
    ]
    for k, v in sorted(summary.items(), key=lambda kv: -kv[1]["ps"]):
        lines.append(f"| {k} | {v['dataset']} | {v['seizures']} | {v['ps']:.3f} | {v['clock']:.3f} "
                     f"| {v['d1']:.3f} | {v['d2']:.3f} |")
    (args.out / "patient_specific.md").write_text("\n".join(lines) + "\n")

    print()
    print(f"Patient-specific AUROC:   {ps_mean:.3f} (95% CI {ps_ci[0]:.3f}-{ps_ci[1]:.3f}), {len(summary)} patients")
    print(f"Patient-specific clock:   {clock_mean:.3f}")
    print(f"EEG beats clock in:       {above_clock} patients")
    print(f"Same patients, cross-patient D1 {d1_same:.3f}, D2 {d2_same:.3f}")
    print(f"Report: {args.out / 'patient_specific.md'}")


if __name__ == "__main__":
    main()

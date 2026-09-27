"""Personalized models (docs/evaluation_methods.md v1.4, Section 11.1). A characterization.

Same 22 patients, the same leave-one-seizure-out folds and buffers, and the same seeds
as the patient-specific test, so every variant is scored on exactly the same test windows:

    ps_eeg_clock       this patient only; D1 features + time of day
    ps_eeg_ctx_clock   this patient only; D1 features + 10 min context + time of day
    general            other patients only (never this one); D1 features + time of day
    general_personal   other patients + this patient's training windows, which carry half
                       of each class's weight; D1 features + time of day

The patient-only EEG model and clock-only model are read from the patient-specific
test (results/d2/patient_specific.csv) for comparison.

Usage, from the repo root with .venv active:
    python scripts/run_personalized.py                   all variants, five seeds (about 2 h)
    python scripts/run_personalized.py --seeds 0         quicker look

Outputs: results/d2/personalized.md and personalized.csv
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
from scipy.stats import wilcoxon
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
from preictal.features.transforms import cache_key, clock_features, context_features, timeline_has_clock  # noqa: E402
from preictal.models.model import build_model, predict_proba  # noqa: E402
from preictal.models.train import TRAIN_CLASSES, blend_weights, load_windows, sample_weights  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

VARIANTS = ("ps_eeg_clock", "ps_eeg_ctx_clock", "general", "general_personal")
LABELS = {"ps_eeg": "This patient only, EEG (patient-specific test)",
          "ps_clock": "This patient only, clock only (patient-specific test)",
          "ps_eeg_clock": "This patient only, EEG + time of day",
          "ps_eeg_ctx_clock": "This patient only, EEG + 10 min context + time of day",
          "general": "Other patients only, EEG + time of day",
          "general_personal": "Other patients + this patient, EEG + time of day"}
OTHERS_EVERY = 6          # other patients' windows 30 s apart (non-overlapping), to keep fits quick


def auroc(y, s):
    y = np.asarray(y, bool)
    return float(roc_auc_score(y, s)) if y.any() and (~y).any() else float("nan")


def fit(X, y, w, seed):
    model = build_model(seed)
    model.fit(X, y, sample_weight=w)
    return model


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, nargs="+", default=None)
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS), choices=VARIANTS)
    ap.add_argument("--features", type=Path, default=REPO / "data" / "processed" / "features")
    ap.add_argument("--out", type=Path, default=REPO / "results" / "d2")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    seeds = args.seeds if args.seeds is not None else cfg["evaluation"]["seeds"]
    step_s = cfg["windows"]["step_s"]
    datasets = tuple(cfg["training"]["datasets"])
    corrections = DEFAULT_CORRECTIONS.read_text() if DEFAULT_CORRECTIONS.exists() else ""
    version = feature_version(cfg, corrections)
    subjects = read_label_report(REPO / "results" / "d1" / "label_report.csv")
    tl_info = json.loads((args.features / "timelines.json").read_text())

    print("Loading features...")
    W = load_windows(args.features, datasets, version=version, keep_per_channel=False)
    clock = clock_features(W.t_end, np.array([timeline_has_clock(k) for k in W.timelines])[W.timeline])
    X_clock = np.hstack([W.X, clock])
    X_ctx_clock = None
    if "ps_eeg_ctx_clock" in args.variants:
        cache = args.features.parent / "d2_cache" / f"train_ctx10r_{version}_{cache_key(W)}.npy"   # shared with run_d2.py
        if cache.exists():
            ctx = np.load(cache)
        else:
            print("  computing 10 min context features (one-off, cached)...")
            ctx = context_features(W.X, W.timeline, W.t_end, 600)
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.save(cache, ctx)
        X_ctx_clock = np.hstack([W.X, ctx, clock])

    patients = []
    for code, subject in enumerate(W.subjects):
        info = subjects.get(subject)
        if info is None or info.role != "train_test":
            continue
        rows = np.flatnonzero(W.subject == code)
        events = [(tl, on) for tl in np.unique(W.timeline[rows]) for on in tl_info[W.timelines[tl]]["eligible_onsets"]]
        if len(events) >= 2 and (W.y[rows] == INTERICTAL).sum() * step_s >= 3600:
            patients.append((subject, code, rows, events))
    pool = {s for s, i in subjects.items() if i.dataset in datasets and i.role == "train_test"}
    print(f"{len(patients)} patients; variants: {', '.join(args.variants)}")

    rows_out = []
    it = tqdm(patients, desc="patients") if tqdm else patients
    for subject, code, rows, events in it:
        t, y, tl = W.t_end[rows], W.y[rows], W.timeline[rows]
        folds = [(i, tr, te) for i, tr, te in patient_folds(t, y, tl, events, rules.preictal_start_s, rules.sph_s,
                                                             rules.interictal_gap_s)
                 if (y[tr] == PREICTAL).any() and (y[tr] == INTERICTAL).any()]
        others = W.rows(pool - {subject})
        others = others[np.isin(W.y[others], TRAIN_CLASSES)]
        others = others[np.round(W.t_end[others] / 5.0).astype(np.int64) % OTHERS_EVERY == 0]
        for seed in seeds:
            preds, labels = defaultdict(list), []
            general = None
            if "general" in args.variants:
                general = fit(X_clock[others], W.y[others], sample_weights(W.y[others], W.subject[others]), seed)
            for i, train, test in folds:
                labels.append(y[test])
                r_tr, r_te = rows[train], rows[test]
                keep = np.isin(y[train], TRAIN_CLASSES)
                r_tr = r_tr[keep]
                w_self = sample_weights(W.y[r_tr], np.zeros(len(r_tr), dtype=int))
                if "ps_eeg_clock" in args.variants:
                    m = fit(X_clock[r_tr], W.y[r_tr], w_self, seed)
                    preds["ps_eeg_clock"].append(predict_proba(m, X_clock[r_te])[:, 0])
                if "ps_eeg_ctx_clock" in args.variants:
                    m = fit(X_ctx_clock[r_tr], W.y[r_tr], w_self, seed)
                    preds["ps_eeg_ctx_clock"].append(predict_proba(m, X_ctx_clock[r_te])[:, 0])
                if general is not None:
                    preds["general"].append(predict_proba(general, X_clock[r_te])[:, 0])
                if "general_personal" in args.variants:
                    wg, wp = blend_weights(W.y[others], W.subject[others], W.y[r_tr], 0.5)
                    m = fit(np.vstack([X_clock[others], X_clock[r_tr]]), np.concatenate([W.y[others], W.y[r_tr]]),
                            np.concatenate([wg, wp]), seed)
                    preds["general_personal"].append(predict_proba(m, X_clock[r_te])[:, 0])
            if not folds:
                continue
            lab = np.concatenate(labels)
            pi = np.isin(lab, (PREICTAL, INTERICTAL))
            row = {"seed": seed, "subject": subject, "dataset": subjects[subject].dataset,
                   "seizures": len(events), "folds_scored": len(folds)}
            for v in args.variants:
                row[v] = auroc(lab[pi] == PREICTAL, np.concatenate(preds[v])[pi])
            rows_out.append(row)

    # earlier patient-specific results for the same patients and seeds
    prev = defaultdict(dict)
    ps_file = args.out / "patient_specific.csv"
    if ps_file.exists():
        for r in csv.DictReader(open(ps_file)):
            if int(r["seed"]) in seeds:
                prev[(r["subject"], int(r["seed"]))] = {"ps_eeg": float(r["auroc"]),
                                                        "ps_clock": float(r["clock_only_auroc"])}
    for r in rows_out:
        r.update(prev.get((r["subject"], r["seed"]), {"ps_eeg": float("nan"), "ps_clock": float("nan")}))

    shown = ["ps_eeg", "ps_clock"] + list(args.variants)
    per_patient = defaultdict(lambda: defaultdict(list))
    for r in rows_out:
        for v in shown:
            per_patient[r["subject"]][v].append(r[v])
    means = {s: {v: float(np.nanmean(vals)) for v, vals in d.items()} for s, d in per_patient.items()}

    def summary(v):
        vals = [m[v] for m in means.values() if not np.isnan(m[v])]
        return float(np.mean(vals)) if vals else float("nan"), bootstrap_ci(vals, 1000, 0)

    def paired(a, b):
        pairs = [(m[a], m[b]) for m in means.values() if not (np.isnan(m[a]) or np.isnan(m[b]))]
        wins = sum(xi > zi for xi, zi in pairs)
        if len(pairs) < 6:
            return float("nan"), wins, len(pairs)
        x, z = zip(*pairs)
        try:
            p = float(wilcoxon(x, z).pvalue)
        except ValueError:
            p = float("nan")
        return p, sum(xi > zi for xi, zi in pairs), len(pairs)

    with open(args.out / "personalized.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows_out)
    lines = ["# Personalized models (characterization)", "",
             f"Generated {datetime.now().isoformat(timespec='seconds')} · seeds {seeds} · {len(means)} patients · "
             "docs/evaluation_methods.md v1.4, Section 11.1. Every variant is scored on the same test windows.", "",
             "| Model | Mean AUROC | 95% CI | Beats the patient's clock-only model | p (vs clock only) |",
             "|---|---|---|---|---|"]
    for v in shown:
        mean, ci = summary(v)
        p, wins, n = paired(v, "ps_clock") if v != "ps_clock" else (float("nan"), 0, 0)
        beat = f"{wins} of {n}" if v != "ps_clock" else "–"
        lines.append(f"| {LABELS[v]} | {mean:.3f} | {ci[0]:.3f}–{ci[1]:.3f} | {beat} | {p:.3g} |")
    comps = [("general_personal", "general"), ("general_personal", "ps_eeg"), ("ps_eeg_clock", "ps_eeg"),
             ("ps_eeg_ctx_clock", "ps_eeg_clock")]
    lines += ["", "## Paired comparisons (per patient, mean over seeds)", "",
              "| Comparison | Patients where the first is higher | Wilcoxon p |", "|---|---|---|"]
    for a, b in comps:
        if a in shown and b in shown:
            p, wins, n = paired(a, b)
            lines.append(f"| {LABELS[a]} vs {LABELS[b]} | {wins} of {n} | {p:.3g} |")
    lines += ["", "## Per patient (mean over seeds)", "",
              "| Patient | Seizures | " + " | ".join(LABELS[v] for v in shown) + " |",
              "|---|---|" + "---|" * len(shown)]
    seizures = {r["subject"]: r["seizures"] for r in rows_out}
    for s in sorted(means, key=lambda s: -means[s].get("general_personal", means[s]["ps_eeg"])):
        lines.append(f"| {s} | {seizures[s]} | " + " | ".join(f"{means[s][v]:.3f}" for v in shown) + " |")
    (args.out / "personalized.md").write_text("\n".join(lines) + "\n")

    print()
    for v in shown:
        mean, ci = summary(v)
        print(f"{LABELS[v]:58s} {mean:.3f}  (95% CI {ci[0]:.3f}-{ci[1]:.3f})")
    if "general_personal" in shown and "general" in shown:
        p, wins, n = paired("general_personal", "general")
        print(f"Adding the patient's own data helped in {wins} of {n} patients (Wilcoxon p {p:.3g})")
    print(f"Report: {args.out / 'personalized.md'}")


if __name__ == "__main__":
    main()

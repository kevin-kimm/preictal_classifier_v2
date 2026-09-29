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

Feature set v2 and the personal baseline (evaluation methods v1.6, Section 11.3):
    --feature-set v2        use data/processed/features_v2 (run extract_features.py --feature-set v2 first)
    --personal-baseline     scale each patient's EEG features by the median and interquartile range of
                            their own interictal training windows (no seizures needed); other patients
                            are scaled by their own interictal windows
    --tag _v2               output file suffix; the report then also compares with the v1 results
    --no-clock              leave out the time-of-day features (evaluation methods v1.8): SeizeIT2's
                            clock times are anonymized, so the design tested there can't use them

Final development round (evaluation methods v1.10, Section 11.4):
    --context-min N         add the mean and slope of each feature over the preceding N min
    --personal-share S      share of each class's weight given to the patient's own windows (default 0.5)
    --cautious-trees        gradient boosting with larger leaves, fewer leaves per tree and L2 regularization
    --compare-to FILE       results/d2 file to compare with (default personalized.csv) ...
    --compare-label TEXT    ... and how to label it

Usage, from the repo root with .venv active:
    python scripts/run_personalized.py                   all variants, five seeds (about 2 h)
    python scripts/run_personalized.py --seeds 0         quicker look

Outputs: results/d2/personalized<tag>.md and personalized<tag>.csv
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
from preictal.features.build_features import FEATURE_VERSION, FEATURE_VERSION_V2, feature_version  # noqa: E402
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


CAUTIOUS = False


def fit(X, y, w, seed):
    if CAUTIOUS:
        from sklearn.ensemble import HistGradientBoostingClassifier
        model = HistGradientBoostingClassifier(random_state=seed, min_samples_leaf=200, max_leaf_nodes=15,
                                               l2_regularization=1.0)
    else:
        model = build_model(seed)
    model.fit(X, y, sample_weight=w)
    return model


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, nargs="+", default=None)
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS), choices=VARIANTS)
    ap.add_argument("--features", type=Path, default=None)
    ap.add_argument("--feature-set", choices=["v1", "v2"], default="v1")
    ap.add_argument("--personal-baseline", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--no-clock", action="store_true")
    ap.add_argument("--context-min", type=int, default=0)
    ap.add_argument("--personal-share", type=float, default=0.5)
    ap.add_argument("--cautious-trees", action="store_true")
    ap.add_argument("--compare-to", default="personalized.csv")
    ap.add_argument("--compare-label", default="feature set v1 with time of day, no baseline")
    ap.add_argument("--out", type=Path, default=REPO / "results" / "d2")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    global CAUTIOUS
    CAUTIOUS = args.cautious_trees
    if args.features is None:
        args.features = REPO / "data" / "processed" / ("features_v2" if args.feature_set == "v2" else "features")

    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    seeds = args.seeds if args.seeds is not None else cfg["evaluation"]["seeds"]
    step_s = cfg["windows"]["step_s"]
    datasets = tuple(cfg["training"]["datasets"])
    corrections = DEFAULT_CORRECTIONS.read_text() if DEFAULT_CORRECTIONS.exists() else ""
    version = feature_version(cfg, corrections, FEATURE_VERSION_V2 if args.feature_set == "v2" else FEATURE_VERSION)
    subjects = read_label_report(REPO / "results" / "d1" / "label_report.csv")
    tl_info = json.loads((args.features / "timelines.json").read_text())

    print("Loading features...")
    W = load_windows(args.features, datasets, version=version, keep_per_channel=False)
    clock = clock_features(W.t_end, np.array([timeline_has_clock(k) for k in W.timelines])[W.timeline])
    n_clock = 0 if args.no_clock else 2
    base = W.X
    if args.context_min:
        cache = args.features.parent / "d2_cache" / f"train_ctx{args.context_min}r_{version}_{cache_key(W)}.npy"
        if cache.exists():
            ctx_extra = np.load(cache)
        else:
            print(f"  computing {args.context_min} min context features (one-off, cached)...")
            ctx_extra = context_features(W.X, W.timeline, W.t_end, args.context_min * 60)
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.save(cache, ctx_extra)
        base = np.hstack([W.X, ctx_extra])
    X_clock = base if args.no_clock else np.hstack([base, clock])
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
        X_ctx_clock = np.hstack([W.X, ctx] + ([] if args.no_clock else [clock]))

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
    print(f"{len(patients)} patients; variants: {', '.join(args.variants)}; feature set {args.feature_set}"
          + ("; personal baseline" if args.personal_baseline else ""))
    mats = {"ps_eeg_clock": X_clock, "general": X_clock, "general_personal": X_clock, "ps_eeg_ctx_clock": X_ctx_clock}

    def scale(M, ref):
        """Scale every column except the clock columns by ref's median and interquartile range."""
        out = M.copy()
        k = M.shape[1] - n_clock
        with np.errstate(all="ignore"):
            med = np.nanmedian(ref[:, :k], axis=0)
            iqr = np.maximum(np.nanpercentile(ref[:, :k], 75, axis=0) - np.nanpercentile(ref[:, :k], 25, axis=0), 1e-3)
        out[:, :k] = (M[:, :k] - med) / iqr
        return out

    scaled_all = {}
    if args.personal_baseline:          # every patient scaled by all of their own interictal windows
        for key in {"clock", "ctx"} & {"ctx" if v == "ps_eeg_ctx_clock" else "clock" for v in args.variants}:
            M = X_ctx_clock if key == "ctx" else X_clock
            S = np.empty_like(M)
            for code in range(len(W.subjects)):
                r = np.flatnonzero(W.subject == code)
                ref = r[W.y[r] == INTERICTAL]
                S[r] = scale(M[r], M[ref]) if len(ref) else M[r]
            scaled_all[key] = S

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
        def patient_matrix(v, train):
            """This patient's rows for variant v, scaled by the fold's training interictal windows if asked."""
            M = mats[v][rows]
            if not args.personal_baseline:
                return M
            ref = train[y[train] == INTERICTAL]
            return scale(M, M[ref])

        def others_matrix(v):
            key = "ctx" if v == "ps_eeg_ctx_clock" else "clock"
            return scaled_all[key][others] if args.personal_baseline else mats[v][others]

        for seed in seeds:
            preds, labels = defaultdict(list), []
            general = None
            if "general" in args.variants:
                general = fit(others_matrix("general"), W.y[others], sample_weights(W.y[others], W.subject[others]), seed)
            for i, train, test in folds:
                labels.append(y[test])
                tr = train[np.isin(y[train], TRAIN_CLASSES)]
                w_self = sample_weights(y[tr], np.zeros(len(tr), dtype=int))
                for v in ("ps_eeg_clock", "ps_eeg_ctx_clock"):
                    if v in args.variants:
                        P = patient_matrix(v, train)
                        m = fit(P[tr], y[tr], w_self, seed)
                        preds[v].append(predict_proba(m, P[test])[:, 0])
                if general is not None:
                    P = patient_matrix("general", train)
                    preds["general"].append(predict_proba(general, P[test])[:, 0])
                if "general_personal" in args.variants:
                    P = patient_matrix("general_personal", train)
                    wg, wp = blend_weights(W.y[others], W.subject[others], y[tr], args.personal_share)
                    m = fit(np.vstack([others_matrix("general_personal"), P[tr]]), np.concatenate([W.y[others], y[tr]]),
                            np.concatenate([wg, wp]), seed)
                    preds["general_personal"].append(predict_proba(m, P[test])[:, 0])
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
    v1_file = args.out / args.compare_to
    v1_shown = []
    if args.tag and v1_file.exists():
        v1 = {}
        for r in csv.DictReader(open(v1_file)):
            if int(r["seed"]) in seeds:
                v1[(r["subject"], int(r["seed"]))] = r
        for v in args.variants:
            key = f"{v}_v1"
            LABELS[key] = LABELS[v].split(",")[0] + f" ({args.compare_label})"
            v1_shown.append(key)
            for r in rows_out:
                old = v1.get((r["subject"], r["seed"]), {})
                r[key] = float(old[v]) if old.get(v) not in (None, "") else float("nan")
    suffix = (f" (feature set {args.feature_set}" + (", personal baseline" if args.personal_baseline else "")
              + (", no time of day" if args.no_clock else "")
              + (f", {args.context_min} min context" if args.context_min else "")
              + (f", personal share {args.personal_share:g}" if args.personal_share != 0.5 else "")
              + (", cautious trees" if args.cautious_trees else "") + ")")
    for v in args.variants:
        LABELS[v] = (LABELS[v].replace(" + time of day", "") if args.no_clock else LABELS[v]) + suffix

    shown = ["ps_eeg", "ps_clock"] + v1_shown + list(args.variants)
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

    with open(args.out / f"personalized{args.tag}.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows_out)
    lines = ["# Personalized models (characterization)", "",
             f"Generated {datetime.now().isoformat(timespec='seconds')} · seeds {seeds} · {len(means)} patients · "
             "docs/evaluation_methods.md v1.4, Section 11.1 (and v1.6, Section 11.3). Every variant is scored on "
             "the same test windows.", "",
             "| Model | Mean AUROC | 95% CI | Beats the patient's clock-only model | p (vs clock only) |",
             "|---|---|---|---|---|"]
    for v in shown:
        mean, ci = summary(v)
        p, wins, n = paired(v, "ps_clock") if v != "ps_clock" else (float("nan"), 0, 0)
        beat = f"{wins} of {n}" if v != "ps_clock" else "–"
        lines.append(f"| {LABELS[v]} | {mean:.3f} | {ci[0]:.3f}–{ci[1]:.3f} | {beat} | {p:.3g} |")
    comps = [("general_personal", "general"), ("general_personal", "ps_eeg"), ("ps_eeg_clock", "ps_eeg"),
             ("ps_eeg_ctx_clock", "ps_eeg_clock")] + [(v, f"{v}_v1") for v in args.variants]
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
    (args.out / f"personalized{args.tag}.md").write_text("\n".join(lines) + "\n")

    print()
    for v in shown:
        mean, ci = summary(v)
        print(f"{LABELS[v]:58s} {mean:.3f}  (95% CI {ci[0]:.3f}-{ci[1]:.3f})")
    if "general_personal" in shown and "general" in shown:
        p, wins, n = paired("general_personal", "general")
        print(f"Adding the patient's own data helped in {wins} of {n} patients (Wilcoxon p {p:.3g})")
    for v in args.variants:
        if f"{v}_v1" in shown:
            p, wins, n = paired(v, f"{v}_v1")
            print(f"{v}: this run beat the comparison ({args.compare_label}) in {wins} of {n} patients "
                  f"(Wilcoxon p {p:.3g})")
    print(f"Report: {args.out / f'personalized{args.tag}.md'}")


if __name__ == "__main__":
    main()

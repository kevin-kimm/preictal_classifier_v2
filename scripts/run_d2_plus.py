"""D2 improvement round, part 2: challengers to the frozen design (docs/evaluation_methods.md v1.25, Section 14.2).

Every arm is the frozen design (other patients + this patient, feature set v2, personal baseline, 10 min
context, no time of day; Section 11.5) with one change. Every arm uses the same patients, the same
leave-one-seizure-out folds and buffers, and is scored on the same test windows with the frozen labels,
so arms can be compared patient by patient:

    frozen        the frozen design itself (must reproduce the frozen results: see --check)
    train_pre10   trained with a 10 min preictal period (test labels stay 30 min); also 20, 45, 60
    train_pre20
    train_pre45
    train_pre60
    pp_length     each patient's training preictal length chosen per fold from 10, 20, 30, 45 and 60 min,
                  by leave-one-seizure-out on that fold's training seizures only (patient-only models)
    pure          trained without windows that straddle two states (start and end in different states)
    slow          plus infra-slow features (scripts/extract_slow_features.py must have been run)
    per_channel   plus each channel's own features, not only their summary across channels (v1.26)
    blend_patient the average of the frozen model's risk and a patient-only model's risk (v1.26)

Each run also saves every scored window (results/d2_plus/<dataset>/scores/), so alarms, warning-window
lengths, smoothing and PPV/NPV can be re-scored afterwards without retraining (scripts/d2_plus_alarms.py).
With --alarms it also saves the out-of-sample scores used to choose each fold's alarm threshold, exactly as
the frozen alarm test does (Section 11.2); that is about 4 times slower.

Usage, from the repo root with .venv active:
    python scripts/run_d2_plus.py --arm frozen --seeds 0 --check          equivalence check (seed 0)
    python scripts/run_d2_plus.py --arm frozen train_pre10 train_pre20 train_pre45 train_pre60
    python scripts/run_d2_plus.py --arm pp_length pure
    python scripts/run_d2_plus.py --arm frozen --alarms --seeds 0 1      saves alarm-calibration scores
    add --dataset seizeit2 for the 25 SeizeIT2 development patients (never the lockbox)

Resumable: finished (arm, patient, seed) results are kept in results/d2_plus/<dataset>/progress.jsonl,
so an interrupted run can simply be started again.

Outputs: results/d2_plus/<dataset>/arms.md and arms.csv (all arms run so far, compared with frozen)
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
from scipy.stats import wilcoxon
from sklearn.metrics import roc_auc_score

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.config import load_config  # noqa: E402
from preictal.data.labels import EXCLUDED, INTERICTAL, PREICTAL, LabelRules  # noqa: E402
from preictal.data.loaders import DEFAULT_CORRECTIONS  # noqa: E402
from preictal.evaluation.d2_plus import alternative_labels, impure, preictal_rules  # noqa: E402
from preictal.evaluation.lopo import read_label_report  # noqa: E402
from preictal.evaluation.metrics import bootstrap_ci  # noqa: E402
from preictal.evaluation.patient_specific import inner_interictal_folds, patient_folds  # noqa: E402
from preictal.features.build_features import FEATURE_VERSION_V2, feature_version  # noqa: E402
from preictal.features.transforms import cache_key, context_features  # noqa: E402
from preictal.models.model import (  # noqa: E402
    CLASS_ORDER, ColumnSubsetModel, build_model, informative_columns, predict_proba,
)
from preictal.models.train import TRAIN_CLASSES, blend_weights, load_windows, sample_weights  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

ARMS = {
    "frozen": {},
    "train_pre10": {"train_pre_min": 10},
    "train_pre20": {"train_pre_min": 20},
    "train_pre45": {"train_pre_min": 45},
    "train_pre60": {"train_pre_min": 60},
    "pp_length": {"pp_length": True},
    "pure": {"pure": True},
    "slow": {"slow": True},
    "per_channel": {"per_channel": True},
    "blend_patient": {"blend_patient": True},
}
ARM_LABELS = {
    "frozen": "Frozen design",
    "train_pre10": "Trained with a 10 min preictal period",
    "train_pre20": "Trained with a 20 min preictal period",
    "train_pre45": "Trained with a 45 min preictal period",
    "train_pre60": "Trained with a 60 min preictal period",
    "pp_length": "Preictal length chosen per patient (nested)",
    "pure": "Trained without windows that straddle two states",
    "slow": "Plus infra-slow features",
    "per_channel": "Plus per-channel features",
    "blend_patient": "Average of the frozen model and a patient-only model",
}
PP_LENGTHS = (10, 20, 30, 45, 60)            # minutes; 30 is the frozen length and wins ties
OTHERS_EVERY = 6                             # other patients' windows 30 s apart, as in the frozen runs
PRE_SAVE_S = 3600.0 + 300.0                  # windows saved before each held-out onset: 60 min + 5 min warm-up
MARGIN = 0.01                                # adoption rule (Section 14.3)


def auroc(y, s):
    y = np.asarray(y, bool)
    return float(roc_auc_score(y, s)) if y.any() and (~y).any() else float("nan")


def fit(X, y, w, seed):
    model = build_model(seed)
    model.fit(X, y, sample_weight=w)
    return model


def fit_patient_only(X, y, seed):
    keep = informative_columns(X)
    model = build_model(seed)
    model.fit(X[:, keep], y, sample_weight=sample_weights(y, np.zeros(len(y), dtype=int)))
    return ColumnSubsetModel(model, keep)


class AverageModel:
    """Averages the class probabilities of several fitted models (blend_patient arm)."""

    def __init__(self, *models):
        self.models = models
        self.classes_ = np.array(CLASS_ORDER)

    def predict_proba(self, X):
        return np.mean([predict_proba(m, X) for m in self.models], axis=0)


def scale(M, ref):
    """Personal baseline (frozen): each column minus ref's median, over ref's interquartile range (floor 0.001)."""
    with np.errstate(all="ignore"):
        med = np.nanmedian(ref, axis=0)
        iqr = np.maximum(np.nanpercentile(ref, 75, axis=0) - np.nanpercentile(ref, 25, axis=0), 1e-3)
    return (M - med) / iqr


def load_slow(W, features_dir: Path, datasets) -> np.ndarray:
    """Infra-slow features aligned to the loaded windows (scripts/extract_slow_features.py)."""
    from preictal.models.train import feature_file
    slow_dir = features_dir.parent / (features_dir.name + "_slow")
    out = None
    for code, name in enumerate(W.recordings):
        idx = np.flatnonzero(W.recording == code)
        f = None
        for ds in datasets:
            cand = feature_file(slow_dir, ds, name)
            if cand.exists():
                f = cand
                break
        if f is None:
            raise FileNotFoundError(f"no infra-slow features for {name} in {slow_dir}; "
                                    "run scripts/extract_slow_features.py first")
        z = np.load(f)
        if out is None:
            out = np.full((len(W.y), z["pooled"].shape[1]), np.nan, dtype=np.float32)
        pos = np.searchsorted(z["starts"], W.starts[idx])
        if np.any(pos >= len(z["starts"])) or not np.allclose(z["starts"][np.minimum(pos, len(z["starts"]) - 1)],
                                                             W.starts[idx]):
            raise ValueError(f"infra-slow windows of {name} don't match the feature windows")
        out[idx] = z["pooled"][pos]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", nargs="+", default=["frozen"], choices=list(ARMS))
    ap.add_argument("--dataset", choices=["chbmit_siena", "seizeit2"], default="chbmit_siena")
    ap.add_argument("--seeds", type=int, nargs="+", default=None)
    ap.add_argument("--alarms", action="store_true", help="also save alarm-calibration scores (about 4x slower)")
    ap.add_argument("--check", action="store_true",
                    help="compare the frozen arm with the committed frozen results; nothing is written to progress")
    ap.add_argument("--patients", nargs="+", default=None, help="only these patients (quick previews)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--report-only", action="store_true", help="rebuild arms.md from progress.jsonl")
    ap.add_argument("--import-frozen", action="store_true",
                    help="record the committed frozen AUROCs (for --seeds) as the frozen arm, after --check passed "
                         "(evaluation methods v1.27); seeds missing from the committed file are left to be run")
    args = ap.parse_args()

    sz2 = args.dataset == "seizeit2"
    out = args.out or REPO / "results" / "d2_plus" / args.dataset
    (out / "scores").mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    seeds = args.seeds if args.seeds is not None else cfg["evaluation"]["seeds"]
    step_s, length_s = cfg["windows"]["step_s"], cfg["windows"]["length_s"]
    progress = out / ("check_progress.jsonl" if args.check else "progress.jsonl")
    if args.check:
        if args.arm != ["frozen"]:
            sys.exit("--check runs the frozen arm only")
        progress.unlink(missing_ok=True)
    done = {}
    if progress.exists():
        for line in progress.read_text().splitlines():
            r = json.loads(line)
            done[(r["arm"], r["subject"], r["seed"], r.get("alarms", False))] = r
    if args.report_only:
        write_report(out, done, args.dataset)
        return
    if args.import_frozen:
        n = import_frozen(out, progress, done, seeds, args.dataset)
        print(f"Imported {n} frozen results into {progress}")
        return

    features = REPO / "data" / "processed" / ("features_seizeit2" if sz2 else "features_v2")
    datasets = ("seizeit2",) if sz2 else tuple(cfg["training"]["datasets"])
    corrections = DEFAULT_CORRECTIONS.read_text() if DEFAULT_CORRECTIONS.exists() else ""
    version = feature_version(cfg, corrections, FEATURE_VERSION_V2)
    subjects = read_label_report(REPO / "results" / "d1" / "label_report.csv")
    test_subjects = sz_pool = None
    if sz2:
        from preictal.data.seizeit2 import FEATURE_CODE, VERSION_TEXT, cohort
        version = feature_version(cfg, VERSION_TEXT, FEATURE_CODE)
        subjects, test_subjects, sz_pool = cohort(REPO, "development")
    tl_info = json.loads((features / "timelines.json").read_text())

    t_start = time.time()
    print("Loading features...")
    # SeizeIT2: development patients only (the lockbox's feature files are never loaded)
    want_pc = any(ARMS[a].get("per_channel") for a in args.arm)
    W = load_windows(features, datasets, subjects=sz_pool if sz2 else None, version=version, keep_per_channel=want_pc)
    per_ch = None
    if want_pc:                       # each channel's features, flattened (absent channels stay missing)
        per_ch = W.per_channel.reshape(len(W.y), -1).astype(np.float32)
        W.per_channel = None
    cache = features.parent / "d2_cache" / f"train_ctx10r_{version}_{cache_key(W)}.npy"     # shared with the frozen runs
    if cache.exists():
        ctx = np.load(cache)
    else:
        print("  computing 10 min context features (one-off, cached)...")
        ctx = context_features(W.X, W.timeline, W.t_end, 600)
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.save(cache, ctx)
    Xf = np.hstack([W.X, ctx])
    pool_subjects = sz_pool if sz2 else {s for s, i in subjects.items() if i.dataset in datasets and i.role == "train_test"}
    label_subjects = sz_pool if sz2 else None

    # ---------------------------------------------------------------- labels each arm needs
    y = W.y                                       # frozen labels: always used for testing and for patient selection
    need = set()
    for a in args.arm:
        spec = ARMS[a]
        if "train_pre_min" in spec:
            need.add(spec["train_pre_min"])
        if spec.get("pp_length"):
            need.update(L for L in PP_LENGTHS if L != 30)
    train_labels = {30: y}
    if need or any(ARMS[a].get("pure") for a in args.arm):
        print("  checking the label mapping against the stored labels...")
        alternative_labels(W, args.dataset, REPO, rules, length_s, step_s, subjects=label_subjects, check_frozen=True)
    for L in sorted(need):
        print(f"  labeling training windows with a {L} min preictal period...")
        YL = alternative_labels(W, args.dataset, REPO, preictal_rules(rules, L), length_s, step_s,
                                subjects=label_subjects)
        if not np.array_equal(YL == INTERICTAL, y == INTERICTAL):
            raise ValueError("a different preictal length changed interictal labels; it may only move windows "
                             "between preictal and excluded")
        train_labels[L] = YL
    impure_mask = None
    if any(ARMS[a].get("pure") for a in args.arm):
        print("  labeling every window at its start, to find windows that straddle two states...")
        y_start = alternative_labels(W, args.dataset, REPO, rules, length_s, step_s, at="start", subjects=label_subjects)
        impure_mask = impure(y, y_start)
        print(f"  {impure_mask.sum():,} of {len(y):,} windows straddle two states "
              f"({impure_mask[y == PREICTAL].mean():.1%} of preictal, {impure_mask[y == INTERICTAL].mean():.2%} of "
              f"interictal, {impure_mask[np.isin(y, (1,))].mean():.1%} of ictal)")
    slow = None
    if any(ARMS[a].get("slow") for a in args.arm):
        slow = load_slow(W, features, datasets)

    every6 = np.round(W.t_end / 5.0).astype(np.int64) % OTHERS_EVERY == 0
    idx6 = np.flatnonzero(every6)
    pos6 = np.full(len(W.y), -1, dtype=np.int64)
    pos6[idx6] = np.arange(len(idx6))

    # other patients' rows are scaled by all their own interictal windows (frozen); only the rows other
    # patients can contribute (every 6th window) are kept, to save memory
    def scaled_all_for(X):
        S = np.empty((len(idx6), X.shape[1]), dtype=X.dtype)
        for code in range(len(W.subjects)):
            r = np.flatnonzero(W.subject == code)
            ref = r[y[r] == INTERICTAL]
            Sr = scale(X[r], X[ref]) if len(ref) else X[r]
            keep = every6[r]
            S[pos6[r[keep]]] = Sr[keep]
        return S

    mats = {"base": Xf}
    if slow is not None:
        mats["slow"] = np.hstack([Xf, slow])
    if per_ch is not None:
        mats["per_channel"] = np.hstack([Xf, per_ch])
    scaled_all = {k: scaled_all_for(v) for k, v in mats.items()}

    patients = []
    for code, subject in enumerate(W.subjects):
        info = subjects.get(subject)
        if info is None or info.role != "train_test" or (test_subjects is not None and subject not in test_subjects):
            continue
        if args.patients and subject not in args.patients and subject.split(":")[-1] not in args.patients:
            continue
        rows = np.flatnonzero(W.subject == code)
        events = [(tl, on) for tl in np.unique(W.timeline[rows]) for on in tl_info[W.timelines[tl]]["eligible_onsets"]]
        if len(events) >= 2 and (y[rows] == INTERICTAL).sum() * step_s >= 3600:
            patients.append((subject, code, rows, events))
    print(f"{len(patients)} patients; arms: {', '.join(args.arm)}; seeds {seeds}"
          + ("; with alarm calibration" if args.alarms else ""))

    def others_rows(subject, ytr_all):
        o = W.rows(pool_subjects - {subject})
        o = o[np.isin(ytr_all[o], TRAIN_CLASSES)]
        return o[every6[o]]

    for arm in args.arm:
        spec = ARMS[arm]
        mkey = "slow" if spec.get("slow") else ("per_channel" if spec.get("per_channel") else "base")
        Mall, Sall = mats[mkey], scaled_all[mkey]
        L_arm = spec.get("train_pre_min", 30)
        ytr_all = train_labels[L_arm].copy()
        if spec.get("pure"):
            ytr_all[impure_mask] = EXCLUDED
        todo = [(p, s) for p in patients for s in seeds if (arm, p[0], s, args.alarms) not in done]
        if not todo:
            print(f"{arm}: already done")
            continue
        print(f"\n{ARM_LABELS[arm]} ({arm})")
        it = tqdm(patients, desc=arm) if tqdm else patients
        for subject, code, rows, events in it:
            if all((arm, subject, s, args.alarms) in done for s in seeds):
                continue
            t, yt, tl = W.t_end[rows], y[rows], W.timeline[rows]
            M = Mall[rows]
            events_sorted = sorted(events)
            others_cache = {}

            def others_for(L):
                """Other patients' training rows and labels: the arm's labels, or length L for pp_length."""
                key = L if spec.get("pp_length") else "arm"
                if key not in others_cache:
                    yl = train_labels[L] if spec.get("pp_length") else ytr_all
                    o = others_rows(subject, yl)
                    others_cache[key] = (o, yl[o])
                return others_cache[key]

            ytr = ytr_all[rows]
            folds = [(i, tr, te) for i, tr, te in patient_folds(t, yt, tl, events, rules.preictal_start_s, rules.sph_s,
                                                                 rules.interictal_gap_s, train_labels=ytr)
                     if (ytr[tr] == PREICTAL).any() and (ytr[tr] == INTERICTAL).any()]
            if not folds:
                continue
            # every window each fold may train on, whatever its label (the buffers only depend on the test
            # windows); pp_length picks its training windows from these with the chosen length's labels
            allowed = {i: tr for i, tr, _ in patient_folds(t, yt, tl, events, rules.preictal_start_s, rules.sph_s,
                                                           rules.interictal_gap_s,
                                                           train_labels=np.full(len(yt), INTERICTAL, yt.dtype))}

            def scaled(ref_rel):
                ref = ref_rel[yt[ref_rel] == INTERICTAL]
                return scale(M, M[ref])

            def train_gp(rel, P, seed, L, ylab):
                rel = rel[np.isin(ylab[rel], TRAIN_CLASSES)]
                o, yo = others_for(L)
                wg, wp = blend_weights(yo, W.subject[o], ylab[rel], 0.5)
                X = np.vstack([Sall[pos6[o]], P[rel]])
                if spec.get("per_channel"):        # channels absent everywhere carry no values; drop such columns
                    keep = informative_columns(X)
                    model = ColumnSubsetModel(fit(X[:, keep], np.concatenate([yo, ylab[rel]]),
                                                  np.concatenate([wg, wp]), seed), keep)
                else:
                    model = fit(X, np.concatenate([yo, ylab[rel]]), np.concatenate([wg, wp]), seed)
                if spec.get("blend_patient"):
                    return AverageModel(model, fit_patient_only(P[rel], ylab[rel], seed))
                return model

            for seed in seeds:
                if (arm, subject, seed, args.alarms) in done:
                    continue
                t0 = time.time()
                save = defaultdict(list)
                labels_test, scores_test, chosen = [], [], []
                for i, train, test in folds:
                    tl_e, onset = events_sorted[i]
                    P = scaled(train)
                    L_use, ylab = L_arm, ytr
                    if spec.get("pp_length"):
                        L_use = choose_length(P, t, yt, tl, allowed[i], events_sorted, i, train_labels, rows, rules,
                                              seed)
                        ylab = train_labels[L_use][rows]
                        train = allowed[i][np.isin(ylab[allowed[i]], TRAIN_CLASSES)]
                        chosen.append(L_use)
                    model = train_gp(train, P, seed, L_use, ylab)
                    pre_long = np.flatnonzero((tl == tl_e) & (t >= onset - PRE_SAVE_S) & (t <= onset - rules.sph_s))
                    score_rows = np.union1d(pre_long, test)
                    s = predict_proba(model, P[score_rows])[:, 0]
                    in_test = np.isin(score_rows, test)
                    labels_test.append(yt[score_rows][in_test])
                    scores_test.append(s[in_test])
                    save["fold"].append(np.full(len(score_rows), i, np.int16))
                    save["onset"].append(np.full(len(score_rows), onset))
                    save["t"].append(t[score_rows])
                    save["tl"].append(tl[score_rows].astype(np.int32))
                    save["label"].append(yt[score_rows])
                    save["score"].append(s.astype(np.float32))
                    save["in_test"].append(in_test)
                    save["in_pre"].append(np.isin(score_rows, pre_long))
                    if impure_mask is not None:
                        save["impure"].append(impure_mask[rows][score_rows])
                    if args.alarms:
                        for k, (inner_train, inner_chunk) in enumerate(inner_interictal_folds(t, yt, tl, train)):
                            P_in = scaled(inner_train)
                            m = train_gp(inner_train, P_in, seed, L_use, ylab)
                            save["cal_fold"].append(np.full(len(inner_chunk), i, np.int16))
                            save["cal_k"].append(np.full(len(inner_chunk), k, np.int8))
                            save["cal_t"].append(t[inner_chunk])
                            save["cal_tl"].append(tl[inner_chunk].astype(np.int32))
                            save["cal_label"].append(yt[inner_chunk])
                            save["cal_score"].append(predict_proba(m, P_in[inner_chunk])[:, 0].astype(np.float32))
                lab = np.concatenate(labels_test)
                sc = np.concatenate(scores_test)
                pi = np.isin(lab, (PREICTAL, INTERICTAL))
                rec = {"arm": arm, "subject": subject, "seed": seed, "alarms": args.alarms, "seizures": len(events),
                       "folds": len(folds), "auroc": auroc(lab[pi] == PREICTAL, sc[pi]),
                       "minutes": round((time.time() - t0) / 60, 2)}
                if impure_mask is not None:
                    pure_test = np.concatenate([x[y_] for x, y_ in zip(save["impure"], save["in_test"])]) == 0
                    rec["auroc_pure_test"] = auroc(lab[pi & pure_test] == PREICTAL, sc[pi & pure_test])
                if chosen:
                    rec["chosen_lengths"] = chosen
                arrays = {k: np.concatenate(v) for k, v in save.items()}
                np.savez_compressed(out / "scores" / f"{arm}_{subject.replace(':', '_')}_seed{seed}"
                                    f"{'_alarms' if args.alarms else ''}.npz",
                                    subject=subject, seizures=len(events), timelines=np.array(W.timelines), **arrays)
                done[(arm, subject, seed, args.alarms)] = rec
                with open(progress, "a") as fh:      # check runs go to check_progress.jsonl
                    fh.write(json.dumps(rec) + "\n")

    if args.check:
        check_against_frozen(out, done, seeds, args.dataset)
        mins = [r["minutes"] for r in done.values()]
        print(f"Run time: {(time.time() - t_start) / 60:.1f} min in total; {np.mean(mins):.1f} min per patient and seed "
              f"(use this to estimate the longer runs)")
        return
    write_report(out, done, args.dataset)
    print(f"\nDone in {(time.time() - t_start) / 3600:.2f} h. Report: {out / 'arms.md'}")


def choose_length(P, t, yt, tl, allowed, events_sorted, held_out, train_labels, rows, rules, seed):
    """pp_length: the training preictal length for this fold, chosen on the fold's training data only.

    Leave one of the fold's training seizures out at a time (same buffers as the outer folds), train a
    patient-only model with each candidate length, and score the held-out training seizure's 30 min preictal
    windows against an interictal chunk of the training data (frozen test labels). The length with the
    highest pooled AUROC wins; ties go to 30 min. Fewer than 2 training seizures: 30 min.
    """
    inner_events = [e for j, e in enumerate(events_sorted) if j != held_out]
    if len(inner_events) < 2:
        return 30
    tt, yy, tll, PA = t[allowed], yt[allowed], tl[allowed], P[allowed]
    scores = {}
    for L in PP_LENGTHS:
        ylab = train_labels[L][rows][allowed]
        labs, preds = [], []
        for _, itr, ite in patient_folds(tt, yy, tll, inner_events, rules.preictal_start_s, rules.sph_s,
                                         rules.interictal_gap_s, train_labels=ylab):
            itr = itr[np.isin(ylab[itr], TRAIN_CLASSES)]
            if not ((ylab[itr] == PREICTAL).any() and (ylab[itr] == INTERICTAL).any()):
                continue
            m = fit_patient_only(PA[itr], ylab[itr], seed)
            labs.append(yy[ite])
            preds.append(predict_proba(m, PA[ite])[:, 0])
        if not labs:
            continue
        lab, pr = np.concatenate(labs), np.concatenate(preds)
        pi = np.isin(lab, (PREICTAL, INTERICTAL))
        scores[L] = auroc(lab[pi] == PREICTAL, pr[pi])
    valid = {L: v for L, v in scores.items() if not np.isnan(v)}
    if not valid:
        return 30
    best = max(valid.values())
    return 30 if valid.get(30) == best else min((L for L, v in valid.items() if v == best), key=lambda L: abs(L - 30))


def frozen_reference(dataset: str) -> Path | None:
    """The committed frozen development AUROC file for a dataset."""
    d2 = REPO / "results" / "d2"
    if dataset == "seizeit2":
        cand = [REPO / "results" / "seizeit2_dev" / "personalized_seizeit2_dev.csv", d2 / "personalized_seizeit2_dev.csv"]
    else:
        cand = sorted(d2.glob("personalized_*ctx10*.csv")) + sorted(d2.glob("personalized_*frozen*.csv"))
        cand = [c for c in cand if "alarms" not in c.name]
    return next((c for c in cand if c.exists()), None)


def import_frozen(out: Path, progress: Path, done: dict, seeds, dataset: str) -> int:
    """Frozen-arm records from the committed results, which --check showed this runner reproduces exactly."""
    ref_file = frozen_reference(dataset)
    if ref_file is None:
        sys.exit("No committed frozen AUROC file found; run the frozen arm instead")
    n = 0
    with open(progress, "a") as fh:
        for r in csv.DictReader(open(ref_file)):
            seed = int(r["seed"])
            if seed not in seeds or r.get("general_personal") in (None, ""):
                continue
            key = ("frozen", r["subject"], seed, False)
            if key in done:
                continue
            rec = {"arm": "frozen", "subject": r["subject"], "seed": seed, "alarms": False,
                   "seizures": int(r.get("seizures", 0) or 0), "folds": int(r.get("folds_scored", r.get("folds", 0)) or 0),
                   "auroc": float(r["general_personal"]), "minutes": 0.0, "imported_from": ref_file.name}
            done[key] = rec
            fh.write(json.dumps(rec) + "\n")
            n += 1
    return n


def check_against_frozen(out: Path, done: dict, seeds, dataset: str):
    """The frozen arm must reproduce the committed frozen AUROC per patient and seed (tolerance 1e-9)."""
    ref_file = frozen_reference(dataset)
    if ref_file is None:
        print("CHECK: no committed frozen AUROC file found in results/d2 "
              "(looked for personalized_*ctx10*.csv / personalized_*frozen*.csv / personalized_seizeit2_dev.csv)")
        return
    ref = {(r["subject"], int(r["seed"])): float(r["general_personal"]) for r in csv.DictReader(open(ref_file))
           if r.get("general_personal") not in (None, "")}
    compared, same = 0, 0
    for (arm, subject, seed, _), r in sorted(done.items()):
        if arm != "frozen" or (subject, seed) not in ref:
            continue
        compared += 1
        ok = abs(r["auroc"] - ref[(subject, seed)]) <= 1e-9
        same += ok
        print(f"{subject:22s} seed {seed}: new {r['auroc']:.6f}  committed {ref[(subject, seed)]:.6f}  "
              f"{'same' if ok else 'DIFFERENT'}")
    print(f"\nCompared with {ref_file.name}")
    if compared and same == compared:
        print(f"CHECK PASSED: {compared} of {compared} results identical")
    else:
        print(f"CHECK FAILED: {same} of {compared} identical" + ("" if compared else " (nothing was compared)"))


def write_report(out: Path, done: dict, dataset: str):
    # AUROC is the same with or without alarm calibration; prefer the run without it, else use the other
    best = {}
    for r in done.values():
        k = (r["arm"], r["subject"], r["seed"])
        if k not in best or (best[k].get("alarms") and not r.get("alarms")):
            best[k] = r
    recs = list(best.values())
    by = defaultdict(lambda: defaultdict(list))
    for r in recs:
        by[r["arm"]][r["subject"]].append(r["auroc"])
    means = {a: {s: float(np.nanmean(v)) for s, v in d.items()} for a, d in by.items()}
    rows_csv, lines = [], [
        f"# D2 improvement round: challengers to the frozen design ({dataset})", "",
        f"Generated {datetime.now().isoformat(timespec='seconds')} · docs/evaluation_methods.md v1.25, Section 14.2. "
        "Every arm is scored on the same test windows with the frozen labels. Adoption rule (Section 14.3): mean "
        f"AUROC at least {MARGIN} above the frozen design on the pooled development patients, and higher in more "
        "than half of them.", "",
        "| Arm | Patients | Seeds | Mean AUROC | 95% CI | Change vs frozen | Higher than frozen in | Wilcoxon p |",
        "|---|---|---|---|---|---|---|---|"]
    order = [a for a in ARMS if a in means]
    for a in order:
        vals = list(means[a].values())
        ci = bootstrap_ci(vals, 1000, 0)
        n_seeds = len({r["seed"] for r in recs if r["arm"] == a})
        diff = wins = n = p = float("nan")
        if a != "frozen" and "frozen" in means:
            common = sorted(set(means[a]) & set(means["frozen"]))
            x = np.array([means[a][s] for s in common])
            z = np.array([means["frozen"][s] for s in common])
            diff, wins, n = float(np.mean(x - z)), int((x > z).sum()), len(common)
            try:
                p = float(wilcoxon(x, z).pvalue) if n >= 6 else float("nan")
            except ValueError:
                p = float("nan")
        lines.append(f"| {ARM_LABELS[a]} | {len(vals)} | {n_seeds} | {np.nanmean(vals):.3f} | {ci[0]:.3f}–{ci[1]:.3f} | "
                     + ("–" if a == "frozen" else f"{diff:+.3f}") + " | "
                     + ("–" if a == "frozen" else f"{wins} of {n}") + " | "
                     + ("–" if a == "frozen" or np.isnan(p) else f"{p:.3g}") + " |")
        rows_csv.append({"arm": a, "patients": len(vals), "seeds": n_seeds, "mean_auroc": np.nanmean(vals),
                         "ci_low": ci[0], "ci_high": ci[1], "diff_vs_frozen": diff, "wins": wins, "n": n, "p": p})
    pure = [r for r in recs if "auroc_pure_test" in r]
    if pure:
        lines += ["", "AUROC on test windows that don't straddle two states (pure arm): "
                  f"{np.nanmean([r['auroc_pure_test'] for r in pure]):.3f}, against "
                  f"{np.nanmean([r['auroc'] for r in pure]):.3f} on all test windows."]
    pp = [r for r in recs if r["arm"] == "pp_length" and "chosen_lengths" in r]
    if pp:
        counts = defaultdict(int)
        for r in pp:
            for L in r["chosen_lengths"]:
                counts[L] += 1
        lines += ["", "Training preictal lengths chosen per fold (pp_length): "
                  + ", ".join(f"{L} min: {counts[L]}" for L in sorted(counts)) + "."]
    lines += ["", "## Per patient (mean over seeds)", "",
              "| Patient | " + " | ".join(order) + " |", "|---|" + "---|" * len(order)]
    for s in sorted(means.get("frozen", next(iter(means.values())))):
        lines.append(f"| {s} | " + " | ".join(f"{means[a].get(s, float('nan')):.3f}" for a in order) + " |")
    (out / "arms.md").write_text("\n".join(lines) + "\n")
    with open(out / "arms.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_csv[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows_csv)
    print("\n".join(lines[:6 + len(order)]))


if __name__ == "__main__":
    main()

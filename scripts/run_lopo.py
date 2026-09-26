"""VT-08 to VT-13: the D1 baseline, evaluated leave-one-patient-out.

Follows docs/evaluation_methods.md. For each seed and each of the eligible test
patients: train on the other CHB-MIT and Siena patients, choose the alarm
threshold on the inner validation patients, then score the test patient.

Usage, from the repo root with .venv active (run scripts/extract_features.py first):
    python scripts/run_lopo.py                       all five seeds
    python scripts/run_lopo.py --seeds 0             one seed, for a quicker first look
    python scripts/run_lopo.py --skip-false-alarm-sets

Outputs in results/d1/:
    lopo_report.md                  summary with pass/fail for VT-08 to VT-13
    lopo_metrics.csv                one row per seed and test patient (VT-11, VT-13)
    fold_log.csv                    inner validation patients and thresholds (VT-08, VT-10)
    reproducibility.json            VT-09
    channel_subset_metrics.csv      VT-12
    false_alarm_sets.csv            false alarms on TUSZ and mental arithmetic
Models trained on all patients are saved to data/models/ (not in Git).
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
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.config import load_config  # noqa: E402
from preictal.data.harmonize import DERIVATIONS  # noqa: E402
from preictal.data.labels import INTERICTAL, LabelRules  # noqa: E402
from preictal.data.loaders import DEFAULT_CORRECTIONS  # noqa: E402
from preictal.evaluation.lopo import check_fold, full_split, make_folds, read_label_report  # noqa: E402
from preictal.evaluation.metrics import (  # noqa: E402
    AlarmResult, Sequence, bootstrap_ci, chance_p_value, choose_threshold, evaluate_all, window_metrics,
)
from preictal.features.build_features import CYTON_DERIVATIONS, feature_version, pool  # noqa: E402
from preictal.models.model import predict_proba  # noqa: E402
from preictal.models.train import fit, load_windows  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


def git_commit() -> str:
    try:
        c = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True,
                           text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "src", "scripts", "configs"], cwd=REPO,
                               capture_output=True, text=True, check=True).stdout.strip()
        return c + (" (uncommitted code changes)" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_unit_tests():
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/test_features.py", "tests/test_alarm.py",
                        "tests/test_lopo.py", "tests/test_metrics.py"], cwd=REPO, capture_output=True, text=True)
    lines = [x for x in r.stdout.strip().splitlines() if x.strip()]
    return r.returncode == 0, (lines[-1] if lines else r.stderr.strip()[-200:])


def sequences(W, rows, scores, tl_info) -> list[Sequence]:
    """Group scored windows by timeline, in time order."""
    out = []
    order = np.lexsort((W.t_end[rows], W.timeline[rows]))
    rows, scores = rows[order], scores[order]
    tl = W.timeline[rows]
    for code in np.unique(tl):
        m = tl == code
        info = tl_info[W.timelines[code]]
        out.append(Sequence(info["subject"], W.t_end[rows][m], scores[m], W.y[rows][m],
                            np.array(info["onsets"], dtype=float), np.array(info["eligible_onsets"], dtype=float)))
    return out


def median(x):
    return float(np.median(x)) if len(x) else float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, nargs="+", default=None)
    ap.add_argument("--features", type=Path, default=REPO / "data" / "processed" / "features")
    ap.add_argument("--out", type=Path, default=REPO / "results" / "d1")
    ap.add_argument("--models", type=Path, default=REPO / "data" / "models")
    ap.add_argument("--skip-false-alarm-sets", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    ev, al = cfg["evaluation"], cfg["alarm"]
    seeds = args.seeds if args.seeds is not None else ev["seeds"]
    step_s = cfg["windows"]["step_s"]
    datasets = tuple(cfg["training"]["datasets"])
    alarm_kw = dict(sph_s=rules.sph_s, horizon_s=rules.preictal_start_s, refractory_s=al["refractory_min"] * 60,
                    smoothing=al["smoothing_windows"], persistence=al["persistence_windows"])
    far_target = ev["far_target_per_24h"]["d1"]
    corrections = DEFAULT_CORRECTIONS.read_text() if DEFAULT_CORRECTIONS.exists() else ""
    version = feature_version(cfg, corrections)
    args.out.mkdir(parents=True, exist_ok=True)

    print("Running unit tests...")
    unit_ok, unit_line = run_unit_tests()
    print(f"  {'PASS' if unit_ok else 'FAIL'}: {unit_line}")

    subjects = read_label_report(args.out / "label_report.csv")
    tl_info = json.loads((args.features / "timelines.json").read_text())
    print("Loading features...")
    W = load_windows(args.features, datasets, version=version)
    print(f"  {len(W.y):,} windows from {len(W.subjects)} subjects")
    missing = sorted(s for s, i in subjects.items()
                     if i.dataset in datasets and i.role == "train_test" and s not in W.subjects)

    rng_subsets = np.random.default_rng(0)
    random_half = {s: np.sort(rng_subsets.choice(len(DERIVATIONS), size=len(DERIVATIONS) // 2, replace=False))
                   for s in sorted(W.subjects)}
    cyton = [DERIVATIONS.index(d) for d in CYTON_DERIVATIONS]

    metric_rows, fold_rows, subset_rows, seed_summary = [], [], [], {}
    leakage, repro = [], {}
    for seed in seeds:
        folds = make_folds(subjects, datasets, seed, ev["inner_validation_fraction"], ev["inner_validation_min_patients"])
        pooled_y, pooled_p, pooled_alarms = [], [], AlarmResult()
        it = tqdm(folds, desc=f"seed {seed}") if tqdm else folds
        for fold in it:
            leakage += check_fold(fold)
            r_train, r_inner, r_test = W.rows(set(fold.train)), W.rows(set(fold.inner)), W.rows({fold.test})
            if len(r_test) == 0:
                continue
            if set(r_train) & set(r_test) or set(r_inner) & set(r_test) or set(r_train) & set(r_inner):
                leakage.append(f"seed {seed} fold {fold.index}: windows shared between sets")
            model = fit(W.X[r_train], W.y[r_train], W.subject[r_train], seed)
            inner_seqs = sequences(W, r_inner, predict_proba(model, W.X[r_inner])[:, 0], tl_info)
            thr, inner_far = choose_threshold(inner_seqs, far_target, step_s, al["threshold_candidates"], **alarm_kw)
            t_fixed = time.time()
            proba = predict_proba(model, W.X[r_test])
            t_scored = time.time()
            wm = window_metrics(W.y[r_test], proba)
            ar = evaluate_all(sequences(W, r_test, proba[:, 0], tl_info), thr, step_s, **alarm_kw)
            pooled_y.append(W.y[r_test])
            pooled_p.append(proba)
            pooled_alarms = pooled_alarms.add(ar)
            ds = subjects[fold.test].dataset
            metric_rows.append({
                "seed": seed, "subject": fold.test, "dataset": ds, "auroc": wm["auroc"], "macro_f1": wm["macro_f1"],
                "confusion": json.dumps(wm["confusion"]), "threshold": thr, "events": ar.n_events,
                "predicted": ar.n_predicted, "alarms": ar.n_alarms, "false_alarms": ar.n_false,
                "far_hours": round(ar.far_hours, 3), "far_per_24h": ar.far_per_24h,
                "time_in_warning": ar.time_in_warning, "sensitivity": ar.sensitivity,
                "median_warning_s": median(ar.warning_times),
                "share_warnings_30s": (np.mean(np.array(ar.warning_times) >= 30) if ar.warning_times else float("nan")),
            })
            fold_rows.append({"seed": seed, "fold": fold.index, "test": fold.test, "inner": ";".join(fold.inner),
                              "n_train_subjects": len(fold.train), "n_train_windows": len(r_train),
                              "threshold": thr, "inner_far_per_24h": inner_far,
                              "threshold_fixed_before_test_scored": t_fixed < t_scored})
            for name, ch in (("all", None), ("random_half", random_half[fold.test]), ("cyton", cyton)):
                p = proba if ch is None else predict_proba(model, pool(W.per_channel[r_test], ch))
                subset_rows.append({"seed": seed, "subject": fold.test, "channels": name,
                                    "auroc": window_metrics(W.y[r_test], p)["auroc"]})
            if seed == seeds[0] and fold.index == 0:
                again = fit(W.X[r_train], W.y[r_train], W.subject[r_train], seed)
                a2 = window_metrics(W.y[r_test], predict_proba(again, W.X[r_test]))["auroc"]
                repro = {"seed": seed, "fold": 0, "subject": fold.test, "auroc_run1": wm["auroc"],
                         "auroc_run2": a2, "difference": abs(wm["auroc"] - a2),
                         "pass": abs(wm["auroc"] - a2) <= 0.005}
        y_all, p_all = np.concatenate(pooled_y), np.concatenate(pooled_p)
        rows = [r for r in metric_rows if r["seed"] == seed]
        chance, pval = chance_p_value(pooled_alarms.n_predicted, pooled_alarms.n_events, pooled_alarms.far_per_24h,
                                      rules.preictal_start_s - rules.sph_s)
        seed_summary[seed] = {
            "mean_patient_auroc": float(np.nanmean([r["auroc"] for r in rows])),
            "pooled_auroc": window_metrics(y_all, p_all)["auroc"],
            "macro_f1_pooled": window_metrics(y_all, p_all)["macro_f1"],
            "sensitivity": pooled_alarms.sensitivity, "far_per_24h": pooled_alarms.far_per_24h,
            "time_in_warning": pooled_alarms.time_in_warning, "events": pooled_alarms.n_events,
            "predicted": pooled_alarms.n_predicted, "chance_probability": chance, "chance_p_value": pval,
            "median_warning_s": median(pooled_alarms.warning_times),
        }

    # ---------------------------------------------------------------- false-alarm sets
    fa_rows, fa_note = [], ""
    fa_sets = [d for d in cfg["training"]["false_alarm_sets"] if (args.features / d).exists()]
    if args.skip_false_alarm_sets:
        fa_note = "skipped (--skip-false-alarm-sets)"
    elif not fa_sets:
        fa_note = "not run: no features yet (python scripts/extract_features.py --datasets tusz mental_arith)"
    else:
        import joblib
        args.models.mkdir(parents=True, exist_ok=True)
        print("Loading false-alarm test sets...")
        fa_windows = {}
        for ds in fa_sets:
            F = load_windows(args.features, (ds,), version=version)
            keep = np.flatnonzero(F.y == INTERICTAL)
            fa_windows[ds] = (F, keep)
            print(f"  {ds}: {len(keep):,} interictal windows")
        for seed in seeds:
            split = full_split(subjects, datasets, seed, ev["inner_validation_fraction"], ev["inner_validation_min_patients"])
            r_train, r_inner = W.rows(set(split.train)), W.rows(set(split.inner))
            model = fit(W.X[r_train], W.y[r_train], W.subject[r_train], seed)
            thr, _ = choose_threshold(sequences(W, r_inner, predict_proba(model, W.X[r_inner])[:, 0], tl_info),
                                      far_target, step_s, al["threshold_candidates"], **alarm_kw)
            joblib.dump(model, args.models / f"d1_seed{seed}.joblib")
            (args.models / f"d1_seed{seed}.json").write_text(json.dumps(
                {"threshold": thr, "inner": split.inner, "feature_version": version}, indent=2))
            for ds in fa_sets:
                F, keep = fa_windows[ds]
                seqs = sequences(F, keep, predict_proba(model, F.X[keep])[:, 0], tl_info)
                per_subject = defaultdict(AlarmResult)
                for s in seqs:
                    per_subject[s.subject] = per_subject[s.subject].add(evaluate_all([s], thr, step_s, **alarm_kw))
                total = evaluate_all(seqs, thr, step_s, **alarm_kw)
                fars = [r.far_per_24h for r in per_subject.values() if r.far_hours >= 0.5]
                fa_rows.append({"seed": seed, "dataset": ds, "threshold": thr, "hours": round(total.far_hours, 2),
                                "false_alarms": total.n_false, "far_per_24h": total.far_per_24h,
                                "patients": len(per_subject), "median_patient_far": median(fars),
                                "p90_patient_far": float(np.percentile(fars, 90)) if fars else float("nan")})

    # ---------------------------------------------------------------- summaries and checks
    per_subject_auroc = defaultdict(list)
    for r in metric_rows:
        per_subject_auroc[r["subject"]].append(r["auroc"])
    subject_means = [float(np.nanmean(v)) for v in per_subject_auroc.values()]
    ci = bootstrap_ci(subject_means, ev["bootstrap_resamples"], 0)
    seed_means = [seed_summary[s]["mean_patient_auroc"] for s in seeds]
    mean_auroc, sd_auroc = float(np.mean(seed_means)), float(np.std(seed_means))
    n_tests = len({r["subject"] for r in metric_rows})
    n_expected = sum(1 for i in subjects.values() if i.dataset in datasets and i.role == "train_test"
                     and i.eligible_test_patient)
    completed = n_tests == n_expected and not any(math.isnan(r["auroc"]) for r in metric_rows)
    mean_far = float(np.mean([seed_summary[s]["far_per_24h"] for s in seeds]))
    thresholds_ok = all(r["threshold_fixed_before_test_scored"] for r in fold_rows)
    subset_means = defaultdict(list)
    for r in subset_rows:
        subset_means[r["channels"]].append(r["auroc"])

    def write(name, rows):
        if not rows:
            return
        with open(args.out / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)

    write("lopo_metrics.csv", metric_rows)
    write("fold_log.csv", fold_rows)
    write("channel_subset_metrics.csv", subset_rows)
    write("false_alarm_sets.csv", fa_rows)
    (args.out / "reproducibility.json").write_text(json.dumps(repro, indent=2))
    (args.out / "lopo_summary.json").write_text(json.dumps(
        {"seeds": seeds, "per_seed": seed_summary, "mean_patient_auroc": mean_auroc, "sd_across_seeds": sd_auroc,
         "ci95": ci, "mean_far_per_24h": mean_far, "feature_version": version}, indent=2))

    def pf(ok):
        return "PASS" if ok else "FAIL"

    all_seeds = seeds == ev["seeds"]
    lines = [
        "# D1 baseline, leave-one-patient-out (VT-08 to VT-13)", "",
        f"Generated {datetime.now().isoformat(timespec='seconds')} · commit {git_commit()} · "
        f"Python {platform.python_version()} · seeds {seeds} · feature version {version}", "",
        "Method: docs/evaluation_methods.md. Unit tests (features, alarms, folds, metrics): "
        f"{pf(unit_ok)}, {unit_line}.", "",
        "## Results", "",
        "| Test | Result |", "|---|---|",
        f"| VT-08 patient separation | {pf(not leakage)}: {len(leakage)} problems in "
        f"{len(fold_rows)} folds; no per-patient normalization in D1 |",
        f"| VT-09 reproducibility | {pf(repro.get('pass', False) and all_seeds)}: AUROC difference "
        f"{repro.get('difference', float('nan')):.4f} on a repeated fold"
        + ("; all five seeds reported |" if all_seeds else f"; only seeds {seeds} run, so not all five seeds are reported |"),
        f"| VT-10 threshold selection | {pf(thresholds_ok)}: every threshold chosen on inner validation "
        "patients and fixed before the test patient was scored |",
        f"| VT-11 cross-patient classification | {pf(completed and ci[0] > 0.5)}: mean per-patient AUROC "
        f"{mean_auroc:.3f} ± {sd_auroc:.3f} across seeds, 95% CI {ci[0]:.3f}–{ci[1]:.3f}; "
        f"{n_tests} of {n_expected} test patients completed. Nice to have (≥ 0.65): "
        f"{'met' if mean_auroc >= 0.65 else 'not met'} |",
        f"| VT-12 channel subsets (characterization) | Mean AUROC: all channels "
        f"{np.nanmean(subset_means['all']):.3f}, random half {np.nanmean(subset_means['random_half']):.3f}, "
        f"Cyton 6 derivations {np.nanmean(subset_means['cyton']):.3f} |",
        f"| VT-13 baseline alarms | {pf(mean_far <= far_target)}: {mean_far:.2f} false alarms per 24 h "
        f"(target ≤ {far_target}) |",
    ]
    if missing:
        lines += ["", f"Subjects in the label report with no feature files: {', '.join(missing)}"]
    lines += ["", "## Per seed", "",
              "| Seed | Mean patient AUROC | Pooled AUROC | Macro F1 | Sensitivity | FAR / 24 h | Time in warning "
              "| Median warning | Chance probability | p (vs chance) |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for s in seeds:
        m = seed_summary[s]
        lines.append(f"| {s} | {m['mean_patient_auroc']:.3f} | {m['pooled_auroc']:.3f} | {m['macro_f1_pooled']:.3f} "
                     f"| {m['predicted']}/{m['events']} ({m['sensitivity']:.2f}) | {m['far_per_24h']:.2f} "
                     f"| {m['time_in_warning']:.3f} | {m['median_warning_s'] / 60:.1f} min "
                     f"| {m['chance_probability']:.3f} | {m['chance_p_value']:.3g} |")
    lines += ["", "## Per test patient (mean over seeds)", "",
              "| Patient | Dataset | AUROC | Sensitivity | FAR / 24 h |", "|---|---|---|---|---|"]
    by_subject = defaultdict(list)
    for r in metric_rows:
        by_subject[r["subject"]].append(r)
    for s, rs in sorted(by_subject.items()):
        lines.append(f"| {s} | {rs[0]['dataset']} | {np.nanmean([r['auroc'] for r in rs]):.3f} "
                     f"| {np.nanmean([r['sensitivity'] for r in rs]):.2f} "
                     f"| {np.nanmean([r['far_per_24h'] for r in rs]):.2f} |")
    lines += ["", "## False-alarm test sets", ""]
    if fa_rows:
        lines += ["Models trained on all CHB-MIT and Siena patients, scored on interictal time only.", "",
                  "| Seed | Dataset | Hours | False alarms | FAR / 24 h | Patients | Median patient FAR | 90th pct |",
                  "|---|---|---|---|---|---|---|---|"]
        lines += [f"| {r['seed']} | {r['dataset']} | {r['hours']} | {r['false_alarms']} | {r['far_per_24h']:.2f} "
                  f"| {r['patients']} | {r['median_patient_far']:.2f} | {r['p90_patient_far']:.2f} |" for r in fa_rows]
    else:
        lines.append(f"Not reported: {fa_note}.")
    if leakage:
        lines += ["", "## Leakage problems", ""] + [f"- {x}" for x in leakage[:50]]
    (args.out / "lopo_report.md").write_text("\n".join(lines) + "\n")

    print()
    print(f"VT-08 separation:     {pf(not leakage)}")
    print(f"VT-09 reproducibility: {pf(repro.get('pass', False))} (difference {repro.get('difference', float('nan')):.4f})")
    print(f"VT-10 thresholds:     {pf(thresholds_ok)}")
    print(f"VT-11 classification: {pf(completed and ci[0] > 0.5)}  mean AUROC {mean_auroc:.3f} ± {sd_auroc:.3f}, "
          f"95% CI {ci[0]:.3f}-{ci[1]:.3f}, {n_tests}/{n_expected} patients")
    print(f"VT-12 channel subsets: all {np.nanmean(subset_means['all']):.3f}, random half "
          f"{np.nanmean(subset_means['random_half']):.3f}, Cyton {np.nanmean(subset_means['cyton']):.3f}")
    print(f"VT-13 alarms:         {pf(mean_far <= far_target)}  FAR {mean_far:.2f} per 24 h, sensitivity "
          f"{np.mean([seed_summary[s]['sensitivity'] for s in seeds]):.2f}")
    if fa_rows:
        for ds in fa_sets:
            v = [r["far_per_24h"] for r in fa_rows if r["dataset"] == ds]
            print(f"False-alarm set {ds}: {np.mean(v):.2f} per 24 h")
    else:
        print(f"False-alarm sets: {fa_note}")
    print(f"Report: {args.out / 'lopo_report.md'}")


if __name__ == "__main__":
    main()

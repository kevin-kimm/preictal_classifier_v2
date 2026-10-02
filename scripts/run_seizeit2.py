"""SeizeIT2 runs of the frozen design, memory-efficient and resumable (docs/evaluation_methods.md v1.17).

The same computations as the dry run (run_personalized.py and run_personalized_alarms.py with
--dataset seizeit2), restructured so the lockbox (about 8 million windows) fits in a laptop's
memory: context features are computed one patient at a time, and only the other patients'
training rows (every 6th window) are kept in memory. Progress is saved after every patient, so
an interrupted run can simply be started again.

    auroc    other patients only, and the frozen design (other patients + this patient):
             leave one seizure out, mean per-patient AUROC
    alarms   the same two models with the frozen alarm settings and thresholds chosen from
             each patient's training data only (targets 5 and 1 false alarms per 24 h)

Usage, from the repo root with .venv active:
    python scripts/run_seizeit2.py --check sub-001 sub-002          reproduce the dry run for these
                                                                    development patients (must match)
    python scripts/run_seizeit2.py --group lockbox --lockbox-run --part auroc    the lockbox run
    python scripts/run_seizeit2.py --group lockbox --lockbox-run --part alarms [--subset N]
                                        --subset N: the alarm part on N patients drawn at random (seed 0)
                                        from those scored in the AUROC part (evaluation methods v1.18)

Outputs: <out>/seizeit2_<group>_<part>.md and .csv, and <out>/seizeit2_<group>_progress.jsonl
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

from preictal.config import load_config  # noqa: E402
from preictal.data.labels import INTERICTAL, PREICTAL, LabelRules  # noqa: E402
from preictal.data.seizeit2 import FEATURE_CODE, VERSION_TEXT, cohort  # noqa: E402
from preictal.evaluation.metrics import (  # noqa: E402
    AlarmResult, Sequence, bootstrap_ci, chance_p_value, choose_threshold_bisect, evaluate_all,
)
from preictal.evaluation.patient_specific import inner_interictal_folds, patient_folds  # noqa: E402
from preictal.features.build_features import feature_version  # noqa: E402
from preictal.features.transforms import context_features  # noqa: E402
from preictal.models.model import build_model, predict_proba  # noqa: E402
from preictal.models.train import TRAIN_CLASSES, blend_weights, load_windows, sample_weights  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

OTHERS_EVERY = 6                     # frozen: other patients' windows 30 s apart
CONTEXT_S = 600                      # frozen: 10 min context
TARGETS = (5.0, 1.0)
SMOOTHING, PERSISTENCE, WARMUP_S = 36, 6, 300.0
VARIANTS = ("general", "general_personal")
LABELS = {"general": "Other patients only (frozen design's features and baseline)",
          "general_personal": "Frozen design: other patients + this patient"}


def scale(M, ref):
    """Personal baseline: minus ref's median, over ref's interquartile range (floor 0.001)."""
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--group", choices=["development", "lockbox"], default="development")
    ap.add_argument("--lockbox-run", action="store_true")
    ap.add_argument("--part", choices=["auroc", "alarms"], default="auroc")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0])
    ap.add_argument("--check", nargs="+", default=None, metavar="SUB",
                    help="development patients whose dry-run results must be reproduced (both parts)")
    ap.add_argument("--subset", type=int, default=None, help="alarm part only: N patients drawn at random (seed 0)")
    ap.add_argument("--features", type=Path, default=REPO / "data" / "processed" / "features_seizeit2")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if args.check:
        args.group = "development"
        args.check = [s for item in args.check for s in item.split()]     # zsh passes "a b" as one argument
    args.out = args.out or REPO / "results" / ("lockbox" if args.group == "lockbox" else "seizeit2_dev")
    args.out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    step_s = cfg["windows"]["step_s"]
    version = feature_version(cfg, VERSION_TEXT, FEATURE_CODE)
    _, test_subjects, pool = cohort(REPO, args.group, args.lockbox_run)
    if args.check:
        test_subjects = {f"seizeit2:{s}" for s in args.check}
    tl_info = json.loads((args.features / "timelines.json").read_text())
    kw = dict(sph_s=rules.sph_s, horizon_s=rules.preictal_start_s, refractory_s=cfg["alarm"]["refractory_min"] * 60,
              smoothing=SMOOTHING, persistence=PERSISTENCE)
    n_cand = cfg["alarm"]["threshold_candidates"]

    print("Loading features...")
    W = load_windows(args.features, ("seizeit2",), version=version, keep_per_channel=False)
    missing = sorted(pool - set(W.subjects))
    if missing:
        sys.exit(f"No features for {len(missing)} patients (e.g. {missing[0]}); run extract_seizeit2.py first")
    print(f"  {len(W.y):,} windows from {len(W.subjects)} patients")

    def patient_matrix(rows):
        """EEG features + 10 min context for one patient's rows (context never crosses patients)."""
        ctx = context_features(W.X[rows], W.timeline[rows], W.t_end[rows], CONTEXT_S)
        return np.hstack([W.X[rows], ctx]).astype(np.float32)

    # other patients' training rows, scaled by each patient's own interictal windows, in global row order
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

    # patients to test (same order and criteria as the dry run)
    patients = []
    for code, subject in enumerate(W.subjects):
        if subject not in test_subjects:
            continue
        rows = np.flatnonzero(W.subject == code)
        events = [(tl, on) for tl in np.unique(W.timeline[rows]) for on in tl_info[W.timelines[tl]]["eligible_onsets"]]
        if len(events) >= 2 and (W.y[rows] == INTERICTAL).sum() * step_s >= 3600:
            patients.append((subject, code, rows, events))
    print(f"{len(patients)} patients qualify; part(s): {'auroc and alarms' if args.check else args.part}; "
          f"seeds {args.seeds}")
    if args.check and len(patients) < len(args.check):
        sys.exit(f"CHECK FAILED: only {len(patients)} of the {len(args.check)} given patients qualified "
                 f"({', '.join(args.check)}); nothing was compared for the others")

    progress = args.out / f"seizeit2_{args.group if not args.check else 'check'}_progress.jsonl"
    done = {}
    if progress.exists() and not args.check:
        for line in progress.read_text().splitlines():
            r = json.loads(line)
            done[(r["part"], r["subject"], r["seed"])] = r
    subset_note = ""
    if args.subset and args.part == "alarms" and not args.check:
        scored = sorted({s for (p, s, seed) in done if p == "auroc" and seed in args.seeds})
        pool_ids = scored if scored else sorted(s for s, *_ in patients)
        chosen = set(np.random.default_rng(0).choice(pool_ids, size=min(args.subset, len(pool_ids)),
                                                     replace=False).tolist())
        patients = [p for p in patients if p[0] in chosen]
        subset_note = (f"Alarm part on a random subset of {len(chosen)} of the {len(pool_ids)} patients scored in the "
                       f"AUROC part (seed 0, evaluation methods v1.18): {', '.join(sorted(chosen))}.")
        print(subset_note)
    parts = ("auroc", "alarms") if args.check else (args.part,)

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
        if all((p, subject, s) in done for p in parts for s in args.seeds):
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

        def train_gp(rel, P, seed):
            rel = rel[np.isin(y[rel], TRAIN_CLASSES)]
            wg, wp = blend_weights(yo, so, y[rel], 0.5)
            return fit(np.vstack([Xo, P[rel]]), np.concatenate([yo, y[rel]]), np.concatenate([wg, wp]), seed)

        for seed in args.seeds:
            todo = [p for p in parts if (p, subject, seed) not in done]
            if not todo:
                continue
            general = fit(Xo, yo, sample_weights(yo, so), seed)
            if "auroc" in todo:
                preds, labels = defaultdict(list), []
                for i, train, test in folds:
                    labels.append(y[test])
                    P = scaled(train)
                    preds["general"].append(predict_proba(general, P[test])[:, 0])
                    preds["general_personal"].append(predict_proba(train_gp(train, P, seed), P[test])[:, 0])
                lab = np.concatenate(labels)
                pi = np.isin(lab, (PREICTAL, INTERICTAL))
                rec = {"part": "auroc", "subject": subject, "seed": seed, "seizures": len(events), "folds": len(folds)}
                for v in VARIANTS:
                    rec[v] = auroc(lab[pi] == PREICTAL, np.concatenate(preds[v])[pi])
                done[("auroc", subject, seed)] = rec
                with open(progress, "a") as fh:
                    fh.write(json.dumps(rec) + "\n")
            if "alarms" in todo:
                totals = {(v, tg): AlarmResult() for v in VARIANTS for tg in TARGETS}
                for i, train, test in folds:
                    tl_e, onset = events_sorted[i]
                    pre_rel = np.flatnonzero((tl == tl_e) & (t >= onset - rules.preictal_start_s - WARMUP_S)
                                             & (t <= onset - rules.sph_s))
                    chunk = test[y[test] == INTERICTAL]
                    for v in VARIANTS:
                        inner_seqs = []
                        for inner_train, inner_chunk in inner_interictal_folds(t, y, tl, train):
                            P_in = scaled(inner_train)
                            m = general if v == "general" else train_gp(inner_train, P_in, seed)
                            inner_seqs += seqs_for(inner_chunk, predict_proba(m, P_in[inner_chunk])[:, 0], t, y, tl)
                        P = scaled(train)
                        model = general if v == "general" else train_gp(train, P, seed)
                        pre = seqs_for(pre_rel, predict_proba(model, P[pre_rel])[:, 0], t, y, tl, [onset])
                        inter = seqs_for(chunk, predict_proba(model, P[chunk])[:, 0], t, y, tl)
                        for tg in TARGETS:
                            thr, _ = choose_threshold_bisect(inner_seqs, tg, step_s, n_cand, **kw)
                            warned = evaluate_all(pre, thr, step_s, **kw)
                            fa = evaluate_all(inter, thr, step_s, **kw)
                            totals[(v, tg)] = totals[(v, tg)].add(AlarmResult(
                                n_events=1, n_predicted=min(warned.n_predicted, 1), n_alarms=fa.n_alarms,
                                n_false=fa.n_false, far_hours=fa.far_hours, n_windows=fa.n_windows,
                                n_warning_windows=fa.n_warning_windows, warning_times=warned.warning_times))
                rec = {"part": "alarms", "subject": subject, "seed": seed, "seizures": len(folds),
                       "results": {f"{v}|{tg:g}": {"warned": r.n_predicted, "false_alarms": r.n_false,
                                                    "hours": r.far_hours} for (v, tg), r in totals.items()}}
                done[("alarms", subject, seed)] = rec
                with open(progress, "a") as fh:
                    fh.write(json.dumps(rec) + "\n")

    # ---------------------------------------------------------------- reports
    names = {s for s, *_ in patients}
    if args.check:
        ok, compared = True, 0
        dev = {r["subject"]: r for r in csv.DictReader(open(args.out / "personalized_seizeit2_dev.csv"))
               if int(r["seed"]) in args.seeds}
        alarms = {(r["subject"], r["variant"], float(r["far_target"])): r for r in csv.DictReader(
            open(args.out / "personalized_alarms_seizeit2_development_frozen.csv")) if int(r["seed"]) in args.seeds}
        for (part, s, seed), r in sorted(done.items()):
            if s not in names:
                continue
            if part == "auroc":
                for v in VARIANTS:
                    same = abs(r[v] - float(dev[s][v])) < 1e-9
                    ok &= same
                    compared += 1
                    print(f"{s} AUROC {v:17s} new {r[v]:.6f}  dry run {float(dev[s][v]):.6f}  {'same' if same else 'DIFFERENT'}")
            else:
                for key, v in r["results"].items():
                    var, tg = key.split("|")
                    old = alarms[(s, var, float(tg))]
                    same = v["warned"] == int(old["warned"]) and v["false_alarms"] == int(old["false_alarms"])
                    ok &= same
                    compared += 1
                    print(f"{s} alarms {var:17s} ≤{tg}: warned {v['warned']}/{r['seizures']} vs {old['warned']}, "
                          f"false alarms {v['false_alarms']} vs {old['false_alarms']}  {'same' if same else 'DIFFERENT'}")
        if compared == 0:
            ok = False
            print("\nNothing was compared.")
        print(f"\nCHECK PASSED: {compared} results identical to the dry run" if ok
              else "\nCHECK FAILED: results differ from the dry run, or nothing was compared")
        return

    recs = [r for (p, s, seed), r in done.items() if p == args.part and s in names and seed in args.seeds]
    stem = args.out / f"seizeit2_{args.group}_{args.part}"
    lines = [f"# SeizeIT2 {args.group}: frozen design, {args.part}", "",
             f"Generated {datetime.now().isoformat(timespec='seconds')} · seeds {args.seeds} · {len(names)} patients · "
             "docs/evaluation_methods.md v1.13 (frozen design) and v1.17 (lockbox protocol).", ""]
    if subset_note:
        lines += [subset_note, ""]
    if args.part == "auroc":
        with open(stem.with_suffix(".csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["seed", "subject", "seizures", "folds"] + list(VARIANTS),
                               lineterminator="\n", extrasaction="ignore")
            w.writeheader()
            w.writerows(recs)
        per = {v: defaultdict(list) for v in VARIANTS}
        for r in recs:
            for v in VARIANTS:
                per[v][r["subject"]].append(r[v])
        lines += ["| Model | Mean AUROC | 95% CI |", "|---|---|---|"]
        means = {}
        for v in VARIANTS:
            vals = [float(np.nanmean(x)) for x in per[v].values()]
            means[v] = vals
            ci = bootstrap_ci(vals, 1000, 0)
            lines.append(f"| {LABELS[v]} | {np.nanmean(vals):.3f} | {ci[0]:.3f}–{ci[1]:.3f} |")
            print(f"{LABELS[v]:60s} {np.nanmean(vals):.3f}  (95% CI {ci[0]:.3f}-{ci[1]:.3f})")
        better = sum(a > b for a, b in zip(means["general_personal"], means["general"]))
        lines.append(f"\nAdding the patient's own data helped in {better} of {len(means['general'])} patients.")
        print(f"Adding the patient's own data helped in {better} of {len(means['general'])} patients")
    else:
        rows_csv = []
        lines += ["| Model | Target | Seizures warned | False alarms per 24 h | Chance | p (vs chance) |",
                  "|---|---|---|---|---|---|"]
        for v in VARIANTS:
            for tg in TARGETS:
                n_ev = sum(r["seizures"] for r in recs)
                n_w = sum(r["results"][f"{v}|{tg:g}"]["warned"] for r in recs)
                fa = sum(r["results"][f"{v}|{tg:g}"]["false_alarms"] for r in recs)
                hours = sum(r["results"][f"{v}|{tg:g}"]["hours"] for r in recs)
                far = 24 * fa / hours if hours else float("nan")
                c, p = chance_p_value(n_w, n_ev, far, rules.preictal_start_s - rules.sph_s)
                rows_csv.append({"variant": v, "far_target": tg, "seizures": n_ev, "warned": n_w, "false_alarms": fa,
                                 "interictal_hours": round(hours, 2), "far_per_24h": far, "chance": c, "p": p})
                lines.append(f"| {LABELS[v]} | ≤ {tg:g} | {n_w}/{n_ev} ({n_w / n_ev:.2f}) | {far:.2f} | {c:.3f} | {p:.3g} |")
                print(f"{LABELS[v]:60s} ≤{tg:g}/24h: warned {n_w}/{n_ev} ({n_w / n_ev:.2f}), FAR {far:.2f}, "
                      f"chance {c:.3f}, p {p:.3g}")
        with open(stem.with_suffix(".csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_csv[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows_csv)
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print(f"Report: {stem.with_suffix('.md')}  ({(time.time() - t_start) / 3600:.1f} h this session)")


if __name__ == "__main__":
    main()

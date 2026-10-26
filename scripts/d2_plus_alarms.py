"""D2 improvement round: alarms, PPV/NPV and confusion matrices from saved scores
(docs/evaluation_methods.md v1.25, Sections 14.4 and 14.5). No model is trained.

Reads the window scores saved by `scripts/run_d2_plus.py --alarms` and scores them the way the frozen alarm
test does (Section 11.2): for each held-out seizure, thresholds are chosen on that fold's out-of-sample
training scores for targets of 5 and 1 false alarms per 24 h; the seizure counts as warned if an alarm
falls between 5 s and the warning window before onset; every alarm on the held-out interictal chunk is
a false alarm.

Reported for each arm:
    alarms        warned share, false alarms per 24 h, chance and p, as in the frozen test
    ppv / npv     alarm level (true alarms over all alarms) and time level (every window: was a warning
                  on, and did a seizure follow within the warning window?), plus PPV and NPV at home
                  seizure rates
    confusion     preictal vs interictal windows at each alarm threshold
    horizons      warning windows of 10, 20, 30, 45 and 60 min (same model and thresholds); alarms more than
                  one warning window before a seizure are counted separately as "early"
    settings      smoothing 1, 12, 36, 72 windows x persistence 1, 3, 6, 12 windows (Section 14.4); the
                  choice rule is applied in d2_plus_alarms.py --choose-settings over all development patients

Usage, from the repo root with .venv active:
    python scripts/d2_plus_alarms.py --arm frozen --check              must reproduce the frozen alarm test
    python scripts/d2_plus_alarms.py --arm frozen
    python scripts/d2_plus_alarms.py --arm frozen --dataset seizeit2
    python scripts/d2_plus_alarms.py --arm frozen --choose-settings    pooled over both development sets

Outputs: results/d2_plus/<dataset>/alarms_<arm>.md and .csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.config import load_config  # noqa: E402
from preictal.data.labels import INTERICTAL, LabelRules  # noqa: E402
from preictal.evaluation.d2_plus import (  # noqa: E402
    TimeConfusion, alarm_ppv_npv, home_ppv_npv, time_confusion, window_confusion,
)
from preictal.evaluation.metrics import (  # noqa: E402
    AlarmResult, Sequence, chance_p_value, choose_threshold_bisect, evaluate_alarms,
)

TARGETS = (5.0, 1.0)
FROZEN_SETTINGS = (36, 6)                     # smoothing, persistence (frozen, Section 11.2)
WARMUP_S = 300.0
HORIZONS_MIN = (10, 20, 30, 45, 60)
SMOOTHINGS = (1, 12, 36, 72)
PERSISTENCES = (1, 3, 6, 12)
HOME_RATES = {"1 a day": 1.0, "1 a week": 1 / 7, "1 a month": 1 / 30}
DATASETS = ("chbmit_siena", "seizeit2")


def sequences(t, tl, y, s, onsets=()):
    """Sequences per timeline, in time order (as the frozen seqs_for)."""
    out = []
    order = np.lexsort((t, tl))
    t, tl, y, s = t[order], tl[order], y[order], s[order]
    on = np.array(onsets, float)
    for c in np.unique(tl):
        m = tl == c
        out.append(Sequence("", t[m], s[m], y[m], on, on))
    return out


def load_scores(out_dir: Path, arm: str):
    """{(subject, seed): npz} for every saved score file of an arm that has alarm calibration."""
    files = sorted((out_dir / "scores").glob(f"{arm}_*_seed*_alarms.npz"))
    res = {}
    for f in files:
        z = dict(np.load(f, allow_pickle=False))
        seed = int(f.stem.split("_seed")[1].split("_")[0])
        res[(str(z["subject"]), seed)] = z
    return res


def fold_results(z, rules, step_s, refractory_s, smoothing, persistence, horizon_s, n_cand):
    """Per fold and target: AlarmResult pieces, early alarms, time confusion and window confusion."""
    kw = dict(sph_s=rules.sph_s, horizon_s=horizon_s, refractory_s=refractory_s, smoothing=smoothing,
              persistence=persistence)
    kw_cal = dict(kw, horizon_s=rules.preictal_start_s)        # thresholds: interictal only, horizon irrelevant
    out = []
    for i in np.unique(z["fold"]):
        m = z["fold"] == i
        onset = float(z["onset"][m][0])
        t, tl, y, s = z["t"][m], z["tl"][m], z["label"][m], z["score"][m].astype(float)
        in_pre, in_test = z["in_pre"][m], z["in_test"][m]
        cm = z["cal_fold"] == i
        cal = []
        for k in np.unique(z["cal_k"][cm]):
            kk = cm & (z["cal_k"] == k)
            cal += sequences(z["cal_t"][kk], z["cal_tl"][kk], z["cal_label"][kk], z["cal_score"][kk].astype(float))
        pre_m = in_pre & (t >= onset - horizon_s - WARMUP_S)
        far_m = in_pre & (t >= onset - 3600.0 - WARMUP_S)              # for early alarms, up to 60 min ahead
        chunk_m = in_test & (y == INTERICTAL)
        pre = sequences(t[pre_m], tl[pre_m], y[pre_m], s[pre_m], [onset])
        far = sequences(t[far_m], tl[far_m], y[far_m], s[far_m], [onset])
        inter = sequences(t[chunk_m], tl[chunk_m], y[chunk_m], s[chunk_m])
        for tg in TARGETS:
            thr, _ = choose_threshold_bisect(cal, tg, step_s, n_cand, **kw_cal)
            warned = AlarmResult()
            for sq in pre:
                warned = warned.add(evaluate_alarms(sq, thr, step_s, **kw))
            fa = AlarmResult()
            for sq in inter:
                fa = fa.add(evaluate_alarms(sq, thr, step_s, **kw))
            early = 0
            for sq in far:
                r = evaluate_alarms(sq, thr, step_s, **kw)
                early += r.n_false            # alarms in the hour before onset that aren't within the window
            tc = TimeConfusion()
            for sq in pre:
                tc = tc.add(time_confusion(sq.times, sq.scores, sq.onsets, thr, rules.sph_s, horizon_s, refractory_s,
                                           smoothing, persistence, keep=sq.times >= onset - horizon_s))
            for sq in inter:
                tc = tc.add(time_confusion(sq.times, sq.scores, sq.onsets, thr, rules.sph_s, horizon_s, refractory_s,
                                           smoothing, persistence))
            wc = window_confusion(y[in_test], s[in_test], thr)
            out.append({"fold": int(i), "target": tg, "threshold": thr, "warned": min(warned.n_predicted, 1),
                        "true_alarms": warned.n_alarms - warned.n_false, "false_alarms": fa.n_false,
                        "hours": fa.far_hours, "early": early, "tc": tc, "wc": wc,
                        "warning_min": (min(warned.warning_times) / 60 if warned.warning_times else float("nan"))})
    return out


def summarize(per_patient: dict, horizon_s: float, rules) -> dict:
    """Pool over patients per seed, then average over seeds. per_patient: {(subject, seed): [fold rows]}."""
    out = {}
    seeds = sorted({s for _, s in per_patient})
    for tg in TARGETS:
        rows_seed = []
        for seed in seeds:
            rs = [r for (subj, s), lst in per_patient.items() if s == seed for r in lst if r["target"] == tg]
            if not rs:
                continue
            n_ev, n_w = len(rs), sum(r["warned"] for r in rs)
            fa, hours = sum(r["false_alarms"] for r in rs), sum(r["hours"] for r in rs)
            ta, early = sum(r["true_alarms"] for r in rs), sum(r["early"] for r in rs)
            far = 24 * fa / hours if hours else float("nan")
            c, p = chance_p_value(n_w, n_ev, far, horizon_s - rules.sph_s)
            pn = alarm_ppv_npv(n_ev, n_w, fa, hours, true_alarms=ta, horizon_h=horizon_s / 3600)
            tc = TimeConfusion()
            for r in rs:
                tc = tc.add(r["tc"])
            wc = {k: sum(r["wc"][k] for r in rs) for k in ("tp", "fp", "fn", "tn")}
            rows_seed.append({"seizures": n_ev, "warned": n_w, "sens": n_w / n_ev, "far": far, "chance": c, "p": p,
                              "false_alarms": fa, "hours": hours,
                              "alarm_ppv": ta / (ta + fa) if ta + fa else float("nan"),
                              "alarm_ppv_with_early": ta / (ta + fa + early) if ta + fa + early else float("nan"),
                              "early_per_seizure": early / n_ev, "npv_counts": pn["npv"],
                              "time_ppv": tc.ppv, "time_npv": tc.npv, "tc": tc, "wc": wc,
                              "patients_warned": len({subj for (subj, s), lst in per_patient.items() if s == seed
                                                      and any(r["warned"] for r in lst if r["target"] == tg)}),
                              "patients": len({subj for (subj, s) in per_patient if s == seed})})
        if not rows_seed:
            continue
        agg = {k: float(np.nanmean([r[k] for r in rows_seed])) for k in rows_seed[0] if k not in ("tc", "wc")}
        agg["p"] = float(np.median([r["p"] for r in rows_seed]))
        agg["wc"] = {k: float(np.mean([r["wc"][k] for r in rows_seed])) for k in ("tp", "fp", "fn", "tn")}
        agg["tc"] = {k: float(np.mean([getattr(r["tc"], k) for r in rows_seed])) for k in ("tp", "fp", "fn", "tn")}
        agg["seeds"] = len(rows_seed)
        out[tg] = agg
    return out


def evaluate_arm(scores, rules, step_s, refractory_s, n_cand, smoothing, persistence, horizon_s):
    per = {}
    for key, z in scores.items():
        per[key] = fold_results(z, rules, step_s, refractory_s, smoothing, persistence, horizon_s, n_cand)
    return per


def check(per, dataset):
    ref_name = {"chbmit_siena": "personalized_alarms_frozen.csv",
                "seizeit2": "personalized_alarms_seizeit2_development_frozen.csv"}[dataset]
    cands = [REPO / "results" / d / ref_name for d in ("d2", "seizeit2_dev")]
    ref_file = next((c for c in cands if c.exists()), None)
    if ref_file is None:
        print(f"CHECK: {ref_name} not found in results/d2 or results/seizeit2_dev")
        return False
    ref = {}
    for r in csv.DictReader(open(ref_file)):
        if r["variant"] == "general_personal":
            ref[(r["subject"], int(r["seed"]), float(r["far_target"]))] = (int(r["warned"]), int(r["false_alarms"]))
    compared = same = 0
    for (subject, seed), rows in sorted(per.items()):
        for tg in TARGETS:
            if (subject, seed, tg) not in ref:
                continue
            rs = [r for r in rows if r["target"] == tg]
            got = (sum(r["warned"] for r in rs), sum(r["false_alarms"] for r in rs))
            exp = ref[(subject, seed, tg)]
            compared += 1
            same += got == exp
            print(f"{subject:22s} seed {seed} ≤{tg:g}: warned {got[0]} vs {exp[0]}, false alarms {got[1]} vs {exp[1]}"
                  f"  {'same' if got == exp else 'DIFFERENT'}")
    ok = compared > 0 and same == compared
    print(f"\nCompared with {ref_name}")
    print(f"CHECK PASSED: {compared} of {compared} identical" if ok else
          f"CHECK FAILED: {same} of {compared} identical" + ("" if compared else " (nothing was compared)"))
    return ok


def fmt_alarm_row(name, tg, a):
    return (f"| {name} | ≤ {tg:g} | {a['sens']:.2f} ({a['warned']:.0f}/{a['seizures']:.0f}) | {a['far']:.2f} | "
            f"{a['chance']:.3f} | {a['p']:.2g} | {a['alarm_ppv']:.3f} | {a['time_ppv']:.3f} | {a['time_npv']:.4f} | "
            f"{a['patients_warned']:.1f} of {a['patients']:.0f} |")


def report(arm, dataset, out_dir, main, horizons, settings, rules):
    lines = [f"# Alarms, PPV and NPV: {arm} ({dataset})", "",
             f"Generated {datetime.now().isoformat(timespec='seconds')} · docs/evaluation_methods.md v1.25, Sections "
             "14.4–14.5. Thresholds from each fold's training data only; frozen alarm settings (risk averaged over 36 "
             "windows, above threshold for 6 in a row, 30 min refractory period) unless stated. Pooled over patients "
             "per seed, then averaged over seeds.", "",
             "## Alarms and PPV/NPV (30 min warning window)", "",
             "| Arm | Target | Seizures warned | False alarms / 24 h | Chance | p | Alarm PPV | Time PPV | Time NPV "
             "| Patients with a seizure warned |", "|---|---|---|---|---|---|---|---|---|---|"]
    for tg, a in main.items():
        lines.append(fmt_alarm_row(arm, tg, a))
    lines += ["", "**Alarm PPV**: true alarms ÷ all alarms. **Time PPV**: of the time a warning was on, the share "
              "followed by a seizure within 30 min. **Time NPV**: of the time without a warning, the share with no "
              "seizure in the next 30 min. Hospital recordings have far more seizures per day than daily life; at "
              "home rates:", "",
              "| Target | " + " | ".join(f"PPV, {k}" for k in HOME_RATES) + " | " + " | ".join(f"NPV, {k}" for k in HOME_RATES)
              + " |", "|---|" + "---|" * (2 * len(HOME_RATES))]
    for tg, a in main.items():
        pv = [home_ppv_npv(a["sens"], a["far"], r) for r in HOME_RATES.values()]
        lines.append(f"| ≤ {tg:g} | " + " | ".join(f"{p:.3f}" for p, _ in pv) + " | "
                     + " | ".join(f"{n:.4f}" for _, n in pv) + " |")
    lines += ["", "## Confusion matrices", "",
              "Windows, at each fold's alarm threshold on the raw score (no smoothing), summed over patients and "
              "averaged over seeds. Positive = preictal.", "",
              "| Target | True preictal, flagged | True preictal, missed | Interictal, flagged | Interictal, not flagged "
              "| Sensitivity | Specificity | PPV | NPV |", "|---|---|---|---|---|---|---|---|---|"]
    for tg, a in main.items():
        w = a["wc"]
        sens = w["tp"] / max(w["tp"] + w["fn"], 1)
        spec = w["tn"] / max(w["tn"] + w["fp"], 1)
        ppv = w["tp"] / max(w["tp"] + w["fp"], 1)
        npv = w["tn"] / max(w["tn"] + w["fn"], 1)
        lines.append(f"| ≤ {tg:g} | {w['tp']:,.0f} | {w['fn']:,.0f} | {w['fp']:,.0f} | {w['tn']:,.0f} | {sens:.3f} "
                     f"| {spec:.3f} | {ppv:.3f} | {npv:.3f} |")
    lines += ["", "Time with and without a warning (alarm logic applied), as windows:", "",
              "| Target | Warning on, seizure ahead | Warning on, none ahead | No warning, seizure ahead "
              "| No warning, none ahead |", "|---|---|---|---|---|"]
    for tg, a in main.items():
        c = a["tc"]
        lines.append(f"| ≤ {tg:g} | {c['tp']:,.0f} | {c['fp']:,.0f} | {c['fn']:,.0f} | {c['tn']:,.0f} |")
    if horizons:
        lines += ["", "## Warning window length (the instructor's comment on timing)", "",
                  "Same model and thresholds; only the warning window changes. Chance is recomputed for each window, "
                  "so shorter windows are judged fairly. \"Early alarms\" are alarms in the hour before a seizure that "
                  "come too early to count for that window length; they aren't in the false-alarm rate, so the PPV "
                  "including them is the stricter one.", "",
                  "| Warning window | Target | Seizures warned | False alarms / 24 h | Chance | p | Times chance "
                  "| Early alarms per seizure | Alarm PPV | PPV incl. early |", "|---|---|---|---|---|---|---|---|---|---|"]
        for H, res in horizons.items():
            for tg, a in res.items():
                ratio = f"{a['sens'] / a['chance']:.1f}" if a["chance"] >= 1e-3 else "–"
                lines.append(f"| {H} min | ≤ {tg:g} | {a['sens']:.2f} | {a['far']:.2f} | {a['chance']:.3f} | {a['p']:.2g} "
                             f"| {ratio} | {a['early_per_seizure']:.2f} | {a['alarm_ppv']:.3f} "
                             f"| {a['alarm_ppv_with_early']:.3f} |")
    if settings:
        lines += ["", "## Alarm settings (target ≤ 5)", "",
                  "| Smoothing (windows) | Persistence (windows) | Seizures warned | False alarms / 24 h | Chance "
                  "| Warned minus chance | p |", "|---|---|---|---|---|---|---|"]
        for (sm, pe), res in settings.items():
            a = res.get(5.0)
            if a:
                mark = " (frozen)" if (sm, pe) == FROZEN_SETTINGS else ""
                lines.append(f"| {sm}{mark} | {pe} | {a['sens']:.3f} | {a['far']:.2f} | {a['chance']:.3f} "
                             f"| {a['sens'] - a['chance']:+.3f} | {a['p']:.2g} |")
    (out_dir / f"alarms_{arm}.md").write_text("\n".join(lines) + "\n")
    rows = []
    for tg, a in main.items():
        rows.append({"arm": arm, "dataset": dataset, "horizon_min": 30, "smoothing": FROZEN_SETTINGS[0],
                     "persistence": FROZEN_SETTINGS[1], "target": tg,
                     **{k: a[k] for k in ("seizures", "warned", "sens", "far", "false_alarms", "hours", "chance", "p",
                                          "alarm_ppv", "alarm_ppv_with_early", "time_ppv", "time_npv", "seeds")}})
    for H, res in (horizons or {}).items():
        for tg, a in res.items():
            rows.append({"arm": arm, "dataset": dataset, "horizon_min": H, "smoothing": FROZEN_SETTINGS[0],
                         "persistence": FROZEN_SETTINGS[1], "target": tg,
                         **{k: a[k] for k in ("seizures", "warned", "sens", "far", "false_alarms", "hours", "chance",
                                              "p", "alarm_ppv", "alarm_ppv_with_early", "time_ppv", "time_npv", "seeds")}})
    for (sm, pe), res in (settings or {}).items():
        for tg, a in res.items():
            rows.append({"arm": arm, "dataset": dataset, "horizon_min": 30, "smoothing": sm, "persistence": pe,
                         "target": tg, **{k: a[k] for k in ("seizures", "warned", "sens", "far", "false_alarms",
                                                             "hours", "chance", "p", "alarm_ppv",
                                                             "alarm_ppv_with_early", "time_ppv", "time_npv",
                                                             "seeds")}})
    with open(out_dir / f"alarms_{arm}.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print("\n".join(lines))
    print(f"\nReport: {out_dir / f'alarms_{arm}.md'}")


def choose_settings(arm: str):
    """Section 14.4 rule: over both development sets pooled, the setting with the largest warned share minus
    chance at the ≤ 5 target, among settings whose pooled false-alarm rate is at most 5 per 24 h. Ties, or no
    setting meeting the rate: the frozen setting."""
    pooled = defaultdict(lambda: {"seizures": 0.0, "warned": 0.0, "false_alarms": 0.0, "hours": 0.0})
    for ds in DATASETS:
        f = REPO / "results" / "d2_plus" / ds / f"alarms_{arm}.csv"
        if not f.exists():
            print(f"missing {f}; run d2_plus_alarms.py --arm {arm} --dataset {ds} first")
            return
        for r in csv.DictReader(open(f)):
            if float(r["target"]) != 5.0 or int(r["horizon_min"]) != 30 or r["far"] in ("", "nan"):
                continue
            key = (int(r["smoothing"]), int(r["persistence"]))
            d = pooled[key]
            for k in ("seizures", "warned", "false_alarms", "hours"):
                d[k] += float(r[k])            # means over seeds, summed over the two datasets
    best, best_val = FROZEN_SETTINGS, None
    lines = ["| Smoothing | Persistence | Warned | False alarms / 24 h | Chance | Warned minus chance |",
             "|---|---|---|---|---|---|"]
    for key, d in sorted(pooled.items()):
        sens = d["warned"] / d["seizures"]
        far = 24 * d["false_alarms"] / d["hours"]
        c, _ = chance_p_value(int(round(d["warned"])), int(round(d["seizures"])), far)
        val = sens - c
        lines.append(f"| {key[0]} | {key[1]} | {sens:.3f} | {far:.2f} | {c:.3f} | {val:+.3f} |")
        if far <= 5.0 and (best_val is None or val > best_val + 1e-12):
            best, best_val = key, val
    lines.append(f"\nChosen: smoothing {best[0]}, persistence {best[1]}"
                 + (" (frozen setting kept)" if best == FROZEN_SETTINGS else ""))
    out = REPO / "results" / "d2_plus" / f"alarm_settings_{arm}.md"
    out.write_text("# Alarm settings choice (Section 14.4)\n\n" + "\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", default="frozen")
    ap.add_argument("--dataset", choices=DATASETS, default="chbmit_siena")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-sweeps", action="store_true", help="skip the warning-window and settings sweeps")
    ap.add_argument("--choose-settings", action="store_true")
    args = ap.parse_args()
    if args.choose_settings:
        choose_settings(args.arm)
        return
    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    step_s = cfg["windows"]["step_s"]
    refractory_s = cfg["alarm"]["refractory_min"] * 60
    n_cand = cfg["alarm"]["threshold_candidates"]
    out_dir = REPO / "results" / "d2_plus" / args.dataset
    scores = load_scores(out_dir, args.arm)
    if not scores:
        sys.exit(f"No saved alarm scores for arm '{args.arm}' in {out_dir / 'scores'}; "
                 f"run scripts/run_d2_plus.py --arm {args.arm} --alarms first")
    print(f"{len(scores)} patient-seed score files for {args.arm}")
    sm, pe = FROZEN_SETTINGS
    per = evaluate_arm(scores, rules, step_s, refractory_s, n_cand, sm, pe, rules.preictal_start_s)
    if args.check:
        check(per, args.dataset)
        return
    main_res = summarize(per, rules.preictal_start_s, rules)
    horizons, settings = {}, {}
    if not args.no_sweeps:
        for H in HORIZONS_MIN:
            hs = H * 60.0
            horizons[H] = main_res if H == 30 else summarize(
                evaluate_arm(scores, rules, step_s, refractory_s, n_cand, sm, pe, hs), hs, rules)
        for s in SMOOTHINGS:
            for p in PERSISTENCES:
                settings[(s, p)] = main_res if (s, p) == FROZEN_SETTINGS else summarize(
                    evaluate_arm(scores, rules, step_s, refractory_s, n_cand, s, p, rules.preictal_start_s),
                    rules.preictal_start_s, rules)
    report(args.arm, args.dataset, out_dir, main_res, horizons, settings, rules)


if __name__ == "__main__":
    main()

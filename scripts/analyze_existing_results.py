"""D2 improvement round, part 1: answers from results already on disk (docs/evaluation_methods.md v1.25,
Section 14.1). No model is trained; it only reads result files and takes a few seconds.

1. Alarm-level PPV and NPV for every alarm result that exists:
       D1 cross-patient            results/d1/lopo_metrics.csv
       frozen design, CHB-MIT/Siena results/d2/personalized_alarms_frozen.csv
       frozen design, SeizeIT2 dev  results/d2/personalized_alarms_seizeit2_development_frozen.csv
       frozen design, lockbox       results/lockbox/seizeit2_lockbox_progress.jsonl (alarm part)
   plus PPV and NPV at home seizure rates of 1 a day, 1 a week and 1 a month.
2. D1 window-level confusion matrices (preictal / ictal / interictal), with window PPV and NPV.
3. Seed variability: how much one patient's AUROC moves between seeds, compared with the overall mean,
   and how much "keeping each patient's best seed" inflates the score (the instructor's comment, p. 6).
4. Channel subsets (VT-12): is 0.573 (random half) vs 0.556 (all channels) more than seed noise?

Usage, from the repo root with .venv active:
    python scripts/analyze_existing_results.py

Output: results/d2_plus/existing_results.md
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.evaluation.d2_plus import alarm_ppv_npv, home_ppv_npv  # noqa: E402
from preictal.evaluation.metrics import chance_p_value  # noqa: E402

HOME_RATES = {"1 a day": 1.0, "1 a week": 1 / 7, "1 a month": 1 / 30}


def fnum(x, nd=3):
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{nd}f}"


def read_csv(p: Path) -> list[dict]:
    with open(p, newline="") as fh:
        return list(csv.DictReader(fh))


# ------------------------------------------------------------------ 1. alarm PPV / NPV

def alarm_sources(repo: Path) -> list[tuple[str, list[dict]]]:
    """(name, list of {seed, variant, target, seizures, warned, false_alarms, hours, true_alarms}) per source."""
    out = []
    d1 = repo / "results" / "d1" / "lopo_metrics.csv"
    if d1.exists():
        rows = []
        for r in read_csv(d1):
            rows.append({"seed": int(r["seed"]), "variant": "D1 cross-patient", "target": 10.0,
                         "seizures": int(float(r["events"])), "warned": int(float(r["predicted"])),
                         "false_alarms": int(float(r["false_alarms"])), "hours": float(r["far_hours"]),
                         "true_alarms": int(float(r["alarms"])) - int(float(r["false_alarms"]))})
        out.append((f"D1, cross-patient ({len({r['subject'] for r in read_csv(d1)})} patients; D1 alarm rule, "
                    "target ≤ 10)", rows))
    for name, fname in (("Frozen design, CHB-MIT and Siena development", "personalized_alarms_frozen.csv"),
                        ("Frozen design, SeizeIT2 development dry run",
                         "personalized_alarms_seizeit2_development_frozen.csv")):
        p = next((repo / "results" / d / fname for d in ("d2", "seizeit2_dev")
                  if (repo / "results" / d / fname).exists()), None)
        if p is not None:
            raw = read_csv(p)
            name = f"{name} ({len({r['subject'] for r in raw})} patients)"
            rows = [{"seed": int(r["seed"]), "variant": r["variant"], "target": float(r["far_target"]),
                     "seizures": int(r["seizures"]), "warned": int(r["warned"]),
                     "false_alarms": int(r["false_alarms"]), "hours": float(r["interictal_hours"]),
                     "true_alarms": None} for r in raw]
            out.append((name, rows))
    lb = repo / "results" / "lockbox" / "seizeit2_lockbox_progress.jsonl"
    if lb.exists():
        rows = []
        for line in lb.read_text().splitlines():
            rec = json.loads(line)
            if rec.get("part") != "alarms" or "results" not in rec:
                continue
            for key, v in rec["results"].items():
                var, tg = key.split("|")
                rows.append({"seed": int(rec.get("seed", 0)), "variant": var, "target": float(tg),
                             "seizures": int(rec["seizures"]), "warned": int(v["warned"]),
                             "false_alarms": int(v["false_alarms"]), "hours": float(v["hours"]), "true_alarms": None})
        if rows:
            n = len({json.loads(x)["subject"] for x in lb.read_text().splitlines()
                     if json.loads(x).get("part") == "alarms"})
            out.append((f"Frozen design, SeizeIT2 lockbox ({n} patients, alarm part)", rows))
    return out


VARIANT_NAMES = {"general": "Other patients only", "general_personal": "Frozen design (other patients + this patient)",
                 "D1 cross-patient": "D1 model"}


def section_alarms(repo: Path) -> list[str]:
    lines = ["## 1. Alarm-level PPV and NPV", "",
             "**PPV** answers: *when the alarm goes off, how often does a seizure follow within 30 min?* "
             "**NPV** answers: *when there is no warning, how often is the next 30 min seizure-free?* Both are "
             "pooled over patients for each seed, then averaged over seeds. Where true alarms weren't saved, PPV "
             "counts warned seizures as the true alarms (at most slightly low), and NPV is approximated from the "
             "counts (see the docstring).", ""]
    sources = alarm_sources(repo)
    if not sources:
        return lines + ["No alarm result files were found.", ""]
    lines += ["| Result | Model | Target | Warned | False alarms / 24 h | Chance | p | PPV | NPV | Seizures / day in the data |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    home = []
    for name, rows in sources:
        groups = defaultdict(list)
        for r in rows:
            groups[(r["variant"], r["target"])].append(r)
        for (var, tg), rs in sorted(groups.items(), key=lambda kv: (kv[0][0] != "general_personal", -kv[0][1])):
            per_seed = defaultdict(lambda: defaultdict(float))
            has_true = all(r["true_alarms"] is not None for r in rs)
            for r in rs:
                d = per_seed[r["seed"]]
                for k in ("seizures", "warned", "false_alarms", "hours"):
                    d[k] += r[k]
                d["true_alarms"] += r["true_alarms"] if has_true else 0
            stats = []
            for d in per_seed.values():
                m = alarm_ppv_npv(int(d["seizures"]), int(d["warned"]), int(d["false_alarms"]), d["hours"],
                                  int(d["true_alarms"]) if has_true else None)
                m["chance"], m["p"] = chance_p_value(int(d["warned"]), int(d["seizures"]), m["far_per_24h"])
                m["n"] = (int(d["warned"]), int(d["seizures"]))
                stats.append(m)
            mean = {k: float(np.nanmean([s[k] for s in stats])) for k in stats[0] if k != "n"}
            mean["p"] = float(np.median([s["p"] for s in stats]))
            lines.append(f"| {name} | {VARIANT_NAMES.get(var, var)} | ≤ {tg:g} | {mean['sensitivity']:.2f} "
                         f"| {mean['far_per_24h']:.2f} | {mean['chance']:.3f} | {mean['p']:.2g} | {mean['ppv']:.3f} "
                         f"| {mean['npv']:.4f} | {mean['seizures_per_day_in_data']:.2f} |")
            if var in ("general_personal", "D1 cross-patient") and tg in (5.0, 10.0):
                home.append((name, VARIANT_NAMES.get(var, var), tg, mean["sensitivity"], mean["far_per_24h"]))
    lines += ["", "### At home seizure rates", "",
              "Hospital recordings have many more seizures per day than daily life (often after medication is "
              "reduced), which flatters PPV. If the same sensitivity and false-alarm rate held at home:", "",
              "| Result | Model | Target | " + " | ".join(f"PPV, {k}" for k in HOME_RATES) + " | "
              + " | ".join(f"NPV, {k}" for k in HOME_RATES) + " |",
              "|---|---|---|" + "---|" * (2 * len(HOME_RATES))]
    for name, var, tg, sens, far in home:
        pv = [home_ppv_npv(sens, far, r) for r in HOME_RATES.values()]
        lines.append(f"| {name} | {var} | ≤ {tg:g} | " + " | ".join(f"{p:.3f}" for p, _ in pv) + " | "
                     + " | ".join(f"{n:.4f}" for _, n in pv) + " |")
    lines += ["", "**Reading these numbers.** NPV is close to 1 for any device, even one that never alarms, "
              "because almost every 30 min stretch is seizure-free. PPV is low whenever seizures are rare, even "
              "for a good device. That is why neither is a pass/fail criterion (evaluation methods, Section 8): "
              "they depend on how often the person has seizures as much as on the device. Sensitivity, false "
              "alarms per 24 h and the chance comparison don't.", ""]
    return lines


# ------------------------------------------------------------------ 2. D1 confusion matrices

def section_confusion(repo: Path) -> list[str]:
    p = repo / "results" / "d1" / "lopo_metrics.csv"
    lines = ["## 2. D1 window-level confusion matrix", ""]
    if not p.exists():
        return lines + ["`results/d1/lopo_metrics.csv` not found.", ""]
    per_seed = defaultdict(lambda: np.zeros((3, 3)))
    for r in read_csv(p):
        if r.get("confusion"):
            per_seed[int(r["seed"])] += np.array(json.loads(r["confusion"]), dtype=float)
    if not per_seed:
        return lines + ["No confusion matrices in the file.", ""]
    C = np.mean(list(per_seed.values()), axis=0)
    names = ("preictal", "ictal", "interictal")
    n_pat = len({r["subject"] for r in read_csv(p)})
    lines += [f"The D1 model's most likely class for every test window, against the true label, summed over the {n_pat} "
              "test patients and averaged over seeds. Rows are the truth, columns the prediction.", "",
              "| True \\ predicted | " + " | ".join(names) + " | Row total |", "|---|---|---|---|---|"]
    for i, n in enumerate(names):
        lines.append(f"| {n} | " + " | ".join(f"{C[i, j]:,.0f}" for j in range(3)) + f" | {C[i].sum():,.0f} |")
    tp, fn = C[0, 0], C[0, 1] + C[0, 2]
    fp, tn = C[2, 0], C[2, 1] + C[2, 2]
    rows_pct = C / C.sum(axis=1, keepdims=True)
    lines += ["", "As shares of each row:", "",
              "| True \\ predicted | " + " | ".join(names) + " |", "|---|---|---|---|"]
    for i, n in enumerate(names):
        lines.append(f"| {n} | " + " | ".join(f"{rows_pct[i, j]:.1%}" for j in range(3)) + " |")
    prev = (tp + fn) / (tp + fn + fp + tn)
    lines += ["", "Preictal vs interictal windows only (\"positive\" = predicted preictal):", "",
              f"* sensitivity {tp / (tp + fn):.3f}, specificity {tn / (tn + fp):.3f};",
              f"* PPV {tp / (tp + fp):.3f} and NPV {tn / (tn + fn):.3f}, with {prev:.1%} of these windows preictal.",
              "", "The most likely class isn't how alarms work (they use a threshold on the preictal probability), "
              "so this shows what the model leans towards rather than alarm performance. The new runs report the "
              "same table at each alarm threshold.", ""]
    return lines


# ------------------------------------------------------------------ 3. seed variability

def seed_table(rows: list[dict], col: str) -> dict | None:
    per = defaultdict(dict)
    for r in rows:
        v = r.get(col)
        if v in (None, ""):
            continue
        v = float(v)
        if not math.isnan(v):
            per[r["subject"]][int(r["seed"])] = v
    seeds = sorted({s for d in per.values() for s in d})
    if len(seeds) < 2:
        return None
    full = {s: d for s, d in per.items() if len(d) == len(seeds)}
    if not full:
        return None
    M = np.array([[full[s][k] for k in seeds] for s in sorted(full)])      # patients x seeds
    seed_means = M.mean(axis=0)
    return {"patients": M.shape[0], "seeds": len(seeds), "mean": float(M.mean()),
            "sd_overall": float(seed_means.std(ddof=1)), "range_overall": float(seed_means.max() - seed_means.min()),
            "sd_patient": float(np.mean(M.std(axis=1, ddof=1))), "range_patient": float(np.mean(M.max(1) - M.min(1))),
            "max_range_patient": float(np.max(M.max(1) - M.min(1))), "best_seed_mean": float(M.max(axis=1).mean())}


def section_seeds(repo: Path) -> list[str]:
    lines = ["## 3. Seed variability", "",
             "The instructor's question: why would the seed matter so much with a large dataset? The table separates two "
             "things. **Overall**: how much the mean over patients moves between seeds. **Per patient**: how much "
             "one patient's AUROC moves. A patient's score rests on a handful of seizures, and windows from the "
             "same seizure are strongly correlated, so the real sample size per patient is the number of seizures "
             "(about 2 to 10), not the number of windows (thousands). Averaging over many patients cancels most of "
             "that noise; picking each patient's best seed adds it all up in one direction.", "",
             "| Result | Patients | Seeds | Mean AUROC | Overall: SD across seeds | Overall: range | Per patient: mean SD "
             "| Per patient: mean range | Per patient: largest range | Mean if each patient's best seed is kept |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    found = False
    d1 = repo / "results" / "d1" / "lopo_metrics.csv"
    candidates = []
    if d1.exists():
        candidates.append(("D1 cross-patient", read_csv(d1), "auroc"))
    for p in sorted((repo / "results" / "d2").glob("personalized*.csv")):
        if "alarms" in p.name:
            continue
        rows = read_csv(p)
        if rows and "general_personal" in rows[0]:
            candidates.append((f"Other patients + this patient (`{p.name}`)", rows, "general_personal"))
    for name, rows, col in candidates:
        t = seed_table(rows, col)
        if t is None:
            continue
        found = True
        lines.append(f"| {name} | {t['patients']} | {t['seeds']} | {t['mean']:.3f} | {t['sd_overall']:.4f} "
                     f"| {t['range_overall']:.3f} | {t['sd_patient']:.3f} | {t['range_patient']:.3f} "
                     f"| {t['max_range_patient']:.3f} | {t['best_seed_mean']:.3f} |")
    if not found:
        lines.append("| no per-seed result files found | | | | | | | | | |")
    lines += ["", "With only 5 seeds, keeping each patient's best already raises the mean; v1 kept the best of 297, "
              "which is why its 0.713 fell to 0.568 when run once (`scripts/demo_best_of_seeds.py`).", ""]
    return lines


# ------------------------------------------------------------------ 4. channel subsets

def section_channels(repo: Path) -> list[str]:
    p = repo / "results" / "d1" / "channel_subset_metrics.csv"
    lines = ["## 4. Channel subsets (VT-12)", ""]
    if not p.exists():
        return lines + ["`results/d1/channel_subset_metrics.csv` not found.", ""]
    per = defaultdict(lambda: defaultdict(dict))         # channels -> subject -> seed -> auroc
    for r in read_csv(p):
        v = float(r["auroc"])
        if not math.isnan(v):
            per[r["channels"]][r["subject"]][int(r["seed"])] = v
    names = [n for n in ("all", "random_half", "cyton") if n in per]
    seeds = sorted({s for d in per["all"].values() for s in d})
    lines += ["| Channels | " + " | ".join(f"Seed {s}" for s in seeds) + " | Mean |", "|---|" + "---|" * (len(seeds) + 1)]
    for n in names:
        vals = [np.nanmean([per[n][subj][s] for subj in per[n] if s in per[n][subj]]) for s in seeds]
        lines.append(f"| {n} | " + " | ".join(f"{v:.3f}" for v in vals) + f" | {np.mean(vals):.3f} |")
    lines += ["", "| Comparison | Patients where the subset is higher | Mean difference | Wilcoxon p |", "|---|---|---|---|"]
    for n in names:
        if n == "all":
            continue
        common = sorted(set(per[n]) & set(per["all"]))
        a = np.array([np.mean(list(per[n][s].values())) for s in common])
        b = np.array([np.mean(list(per["all"][s].values())) for s in common])
        try:
            pval = float(wilcoxon(a, b).pvalue)
        except ValueError:
            pval = float("nan")
        lines.append(f"| {n} vs all | {(a > b).sum()} of {len(common)} | {np.mean(a - b):+.3f} | {fnum(pval)} |")
    lines += ["", "A model at AUROC 0.556 has almost no signal, so which channels it sees barely matters, and a "
              "difference of about 0.015 is within patient-to-patient noise unless the p value says otherwise. "
              "Fewer channels can also make the pooled features (mean, SD, min and max across channels) less "
              "noisy, which can help a near-chance model slightly.", ""]
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, default=REPO)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    out = args.out or args.repo / "results" / "d2_plus"
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# Answers from existing results (D2 improvement round, part 1)", "",
             f"Generated {datetime.now().isoformat(timespec='seconds')} · docs/evaluation_methods.md v1.25, "
             "Section 14.1. No model was trained; every number comes from result files already committed.", ""]
    lines += section_alarms(args.repo) + section_confusion(args.repo) + section_seeds(args.repo) + section_channels(args.repo)
    (out / "existing_results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nReport: {out / 'existing_results.md'}")


if __name__ == "__main__":
    main()

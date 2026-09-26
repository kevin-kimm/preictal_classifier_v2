"""VT-06 and VT-07: build the labels and the per-patient label report.

Runs the VT-06 unit tests, labels every recording (see src/preictal/data/labels.py),
and summarizes the result per patient.

Usage, from the repo root with .venv active:
    python scripts/build_labels.py

Outputs:
    results/d1/label_report.md      summary, VT-07 checks, and the D-6 decision
    results/d1/label_report.csv     one row per patient (VT-07 evidence)
    data/processed/label_intervals.csv   label intervals per recording (not in Git)
    data/processed/events.csv            every seizure event with its eligibility (not in Git)
    data/processed/timelines.csv         where each recording sits on its timeline (not in Git)
"""

from __future__ import annotations

import argparse
import csv
import platform
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.config import load_config  # noqa: E402
from preictal.data.labels import (  # noqa: E402
    DAY, LABEL_NAMES, LabelRules, build_timelines, label_intervals, window_labels,
)
from preictal.data.loaders import discover  # noqa: E402

PREDICTION_DATASETS = ("chbmit", "siena", "tusz")


def git_commit() -> str:
    try:
        c = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                           capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "src", "scripts", "configs"], cwd=REPO,
                               capture_output=True, text=True, check=True).stdout.strip()
        return c + (" (uncommitted code changes)" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_unit_tests():
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/test_labels.py"], cwd=REPO,
                       capture_output=True, text=True)
    lines = [x for x in r.stdout.strip().splitlines() if x.strip()]
    return r.returncode == 0, (lines[-1] if lines else r.stderr.strip()[-200:])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", type=Path, default=REPO / "data" / "raw")
    ap.add_argument("--out", type=Path, default=REPO / "results" / "d1")
    ap.add_argument("--processed", type=Path, default=REPO / "data" / "processed")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    args.processed.mkdir(parents=True, exist_ok=True)

    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    length_s, step_s = cfg["windows"]["length_s"], cfg["windows"]["step_s"]

    print("Running VT-06 unit tests...")
    unit_ok, unit_line = run_unit_tests()
    print(f"  {'PASS' if unit_ok else 'FAIL'}: {unit_line}")

    notes = []
    recs = discover(args.data_root, notes=notes)
    print(f"{len(recs)} recordings found; building timelines...")
    timelines = build_timelines(recs, rules)

    per_subject = defaultdict(lambda: {"dataset": "", "role": "", "recordings": 0, "hours": 0.0,
                                       "seizures": 0, "excluded_annotations": 0, "events": 0,
                                       "eligible": 0, **{f"{n}_h": 0.0 for n in LABEL_NAMES},
                                       **{f"{n}_windows": 0 for n in LABEL_NAMES}})
    interval_rows, event_rows, timeline_rows = [], [], []
    bad_intervals, bad_windows, too_short = [], [], 0
    coverage_buckets = Counter()
    timeline_notes = []
    multi_day, unanchored = Counter(), Counter()

    for tl in timelines:
        s = per_subject[tl.subject]
        s["dataset"], s["role"] = tl.dataset, tl.role
        s["events"] += len(tl.events)
        s["eligible"] += sum(e.eligible for e in tl.events)
        timeline_notes += tl.notes
        starts = {p.rec.rel_path: p.start for p in tl.placed}
        if tl.placed and max(p.end for p in tl.placed) - min(p.start for p in tl.placed) > DAY:
            multi_day[tl.dataset] += 1
        for e in tl.events:
            if not e.eligible:
                coverage_buckets[(tl.dataset, "none recorded" if e.coverage == 0 else
                                  "under 50%" if e.coverage < 0.5 else "50-90%")] += 1
            event_rows.append([tl.dataset, tl.subject, e.recording, round(e.onset - starts.get(e.recording, 0), 3),
                               round(e.offset - e.onset, 3), e.n_seizures, round(e.coverage, 4), e.eligible])
        for p in tl.placed:
            if not p.anchored:
                unanchored[tl.dataset] += 1
            s["recordings"] += 1
            s["hours"] += p.duration / 3600
            s["seizures"] += len(p.rec.seizures)
            s["excluded_annotations"] += len(p.rec.excluded)
            timeline_rows.append([tl.dataset, tl.subject, "|".join(map(str, tl.key)), p.rec.rel_path,
                                  round(p.start, 3), round(p.duration, 3), p.anchored])
            ivals = label_intervals(p, tl, rules)
            total = sum(b - a for a, b, _ in ivals)
            if abs(total - p.duration) > 1e-6:
                bad_intervals.append(p.rec.rel_path)
            for a, b, name in ivals:
                s[f"{name}_h"] += (b - a) / 3600
                interval_rows.append([tl.dataset, tl.subject, p.rec.rel_path, round(a, 3), round(b, 3), name])
            w_starts, w_labels = window_labels(p, tl, rules, length_s, step_s)
            if len(w_starts) == 0:
                too_short += 1
            elif not 0 <= p.duration - (w_starts[-1] + length_s) < step_s:
                bad_windows.append(p.rec.rel_path)
            for k, n in zip(*np.unique(w_labels, return_counts=True)):
                s[f"{LABEL_NAMES[k]}_windows"] += int(n)

    # eligible test patients (plan, Section 3) and the D-6 decision
    for s in per_subject.values():
        s["eligible_test_patient"] = (s["role"] == "train_test" and s["eligible"] >= 1
                                      and s["interictal_h"] >= 1.0)
    eligible_patients = sum(s["eligible_test_patient"] for s in per_subject.values())
    threshold = cfg["evaluation"]["grouped_cv_patient_threshold"]
    scheme = "grouped_10fold" if eligible_patients > threshold else "lopo"

    # write outputs
    def write(path, header, rows):
        with open(path, "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(header)
            w.writerows(rows)

    write(args.processed / "label_intervals.csv",
          ["dataset", "subject", "recording", "start_s", "end_s", "label"], interval_rows)
    write(args.processed / "events.csv",
          ["dataset", "subject", "recording", "onset_s", "duration_s", "n_seizures", "coverage", "eligible"],
          event_rows)
    write(args.processed / "timelines.csv",
          ["dataset", "subject", "timeline", "recording", "start_on_timeline_s", "duration_s", "anchored"],
          timeline_rows)
    cols = ["dataset", "role", "recordings", "hours", "seizures", "excluded_annotations", "events", "eligible",
            "eligible_test_patient", *[f"{n}_h" for n in LABEL_NAMES], *[f"{n}_windows" for n in LABEL_NAMES]]
    write(args.out / "label_report.csv", ["subject", *cols],
          [[subj, *[round(s[c], 3) if isinstance(s[c], float) else s[c] for c in cols]]
           for subj, s in sorted(per_subject.items())])

    # dataset summary
    ds_sum = defaultdict(Counter)
    for s in per_subject.values():
        d = ds_sum[s["dataset"]]
        d["patients"] += 1
        d["false_alarm_only"] += s["role"] == "false_alarm_only"
        d["eligible_test_patients"] += s["eligible_test_patient"]
        for c in ("recordings", "seizures", "events", "eligible", *[f"{n}_h" for n in LABEL_NAMES],
                  *[f"{n}_windows" for n in LABEL_NAMES]):
            d[c] += s[c]

    subjects_expected = {r.subject for r in recs if r.dataset != "tuar"}
    every_patient = subjects_expected == set(per_subject)
    vt07 = unit_ok and every_patient and not bad_intervals and not bad_windows
    lines = [
        "# Labels (VT-06, VT-07)", "",
        f"Generated {datetime.now().isoformat(timespec='seconds')} · commit {git_commit()} · "
        f"Python {platform.python_version()} · windows {length_s} s, step {step_s} s", "",
        "## Results", "",
        "| Test | Result |", "|---|---|",
        f"| VT-06 labeling rules (unit tests, `tests/test_labels.py`) | {'PASS' if unit_ok else 'FAIL'}: {unit_line} |",
        f"| VT-07 a row for every patient | {'PASS' if every_patient else 'FAIL'}: "
        f"{len(per_subject)} of {len(subjects_expected)} patients |",
        f"| VT-07 label durations add up to each recording's length | "
        f"{'PASS' if not bad_intervals else 'FAIL'}: {len(bad_intervals)} mismatches (label intervals, exact) |",
        f"| VT-07 windows cover each recording to within one window | "
        f"{'PASS' if not bad_windows else 'FAIL'}: {len(bad_windows)} mismatches; "
        f"{too_short} recordings shorter than one window |", "",
        "## Per dataset", "",
        "| Dataset | Patients | Recordings | Seizures | Events (after merging) | Eligible events "
        "| Eligible test patients | Preictal h | Ictal h | Interictal h | Excluded h |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for ds, d in sorted(ds_sum.items()):
        pats = f"{d['patients']}" + (f" ({d['false_alarm_only']} false-alarm only)" if d["false_alarm_only"] else "")
        lines.append(f"| {ds} | {pats} | {d['recordings']} | {d['seizures']} | {d['events']} | {d['eligible']} "
                     f"| {d['eligible_test_patients']} | {d['preictal_h']:.1f} | {d['ictal_h']:.1f} "
                     f"| {d['interictal_h']:.1f} | {d['excluded_h']:.1f} |")
    lines += ["", f"Windows ({length_s} s, step {step_s} s):", "",
              "| Dataset | Preictal | Ictal | Interictal | Excluded |", "|---|---|---|---|---|"]
    for ds, d in sorted(ds_sum.items()):
        lines.append(f"| {ds} | {d['preictal_windows']:,} | {d['ictal_windows']:,} | {d['interictal_windows']:,} "
                     f"| {d['excluded_windows']:,} |")
    lines += ["", "## Cross-validation scheme (D-6)", "",
              f"Eligible test patients (at least one eligible seizure and at least 1 h interictal): "
              f"**{eligible_patients}**. The D-6 threshold is {threshold}, so the scheme is "
              f"**{'patient-grouped 10-fold cross-validation' if scheme == 'grouped_10fold' else 'leave-one-patient-out'}**.",
              "", "## Why seizures were not eligible", "",
              "An event is eligible if at least 90% of its 30 min preictal period is recorded.", "",
              "| Dataset | None of the preictal period recorded | Under 50% | 50-90% |", "|---|---|---|---|"]
    for ds in PREDICTION_DATASETS:
        lines.append(f"| {ds} | {coverage_buckets[(ds, 'none recorded')]} | {coverage_buckets[(ds, 'under 50%')]} "
                     f"| {coverage_buckets[(ds, '50-90%')]} |")
    same_time = Counter(n.split("/")[0].rsplit("_v", 1)[0] for n in timeline_notes if "same start time" in n)
    uncertain = [n for n in timeline_notes if "position unknown" in n]
    lines += ["", "## Timelines", "",
              "Recordings are placed in time using their EDF start times. A recording is labeled on its own "
              "when its position can't be trusted; none of its time is then interictal if its patient "
              "(or TUSZ session) has seizures.", "",
              "Recordings labeled on their own: "
              + (", ".join(f"{k} {v}" for k, v in sorted(unanchored.items())) or "none") + ".",
              "Groups (patients or TUSZ sessions) whose recordings all report the same start time: "
              + (", ".join(f"{k} {v}" for k, v in sorted(same_time.items())) or "none") + ".",
              f"Recordings that would start more than 60 s before the previous one ends: {len(uncertain)}.",
              "Timelines spanning more than one day: "
              + (", ".join(f"{k} {v}" for k, v in sorted(multi_day.items())) or "none") + "."]
    if uncertain:
        lines += [""] + [f"- {n}" for n in uncertain[:30]]
        if len(uncertain) > 30:
            lines.append(f"- ... and {len(uncertain) - 30} more")
    for label, items in (("Label interval mismatches", bad_intervals), ("Window coverage mismatches", bad_windows)):
        if items:
            lines += ["", f"{label}:", ""] + [f"- {x}" for x in items[:30]]
    (args.out / "label_report.md").write_text("\n".join(lines) + "\n")

    print()
    for ds, d in sorted(ds_sum.items()):
        print(f"{ds:13s} patients {d['patients']:4d}  events {d['events']:5d}  eligible {d['eligible']:5d}  "
              f"eligible test patients {d['eligible_test_patients']:4d}  "
              f"preictal {d['preictal_h']:7.1f} h  interictal {d['interictal_h']:8.1f} h")
    print(f"\nEligible test patients: {eligible_patients} -> scheme: {scheme} (D-6 threshold {threshold})")
    print(f"VT-06 unit tests: {'PASS' if unit_ok else 'FAIL'} ({unit_line})")
    print(f"VT-07: {'PASS' if vt07 else 'FAIL'} ({len(per_subject)} patients, {len(bad_intervals)} interval "
          f"mismatches, {len(bad_windows)} window mismatches)")
    print(f"Report: {args.out / 'label_report.md'}")


if __name__ == "__main__":
    main()

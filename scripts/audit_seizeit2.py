"""Blind feasibility audit of the SeizeIT2 lockbox (docs/evaluation_methods.md v1.7, Section 12).

Checks that SeizeIT2 can be used, without looking at anything that could shape the
design: it reads only file listings, EDF headers (channel names, sampling rates,
durations, start times) and the column names and event categories of the annotation
files. It never prints seizure timings, never reads EEG samples, and reports seizure
numbers only as totals across the whole dataset.

Usage, from the repo root with .venv active:
    python scripts/audit_seizeit2.py

Output: results/lockbox/seizeit2_feasibility.md (committed, as a record of what was looked at)
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.data.edf import read_header  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

ROOT = REPO / "data" / "raw" / "seizeit2_v1.1.0"
NON_SEIZURE = {"bckg", "background", "n/a", "", "impd", "artifact", "artefact"}


def modality(path: Path) -> str:
    for part in path.parts[::-1]:
        if part in ("eeg", "ecg", "emg", "mov"):
            return part
    return "other"


def main():
    if not ROOT.exists():
        sys.exit(f"{ROOT} not found")
    files = [p for p in ROOT.rglob("*") if p.is_file()]
    subjects = sorted({m.group(0) for p in files if (m := re.search(r"sub-[A-Za-z0-9]+", str(p)))})
    sessions = {(m1.group(0), m2.group(0)) for p in files
                if (m1 := re.search(r"sub-[A-Za-z0-9]+", str(p))) and (m2 := re.search(r"ses-[A-Za-z0-9]+", str(p)))}
    by_ext = Counter(p.suffix.lower() for p in files)
    edfs = sorted(p for p in files if p.suffix.lower() == ".edf")

    # EDF headers only
    labels, rates, units = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    hours, n_ok, bad, times = Counter(), Counter(), [], Counter()
    hours_by_subject = defaultdict(float)
    it = tqdm(edfs, desc="EDF headers") if tqdm else edfs
    for p in it:
        mod = modality(p)
        try:
            h = read_header(p)
        except Exception as e:  # noqa: BLE001 - report any unreadable file
            bad.append(f"{p.relative_to(ROOT)}: {e}")
            continue
        n_ok[mod] += 1
        hours[mod] += h.duration_s / 3600
        for i, lab in enumerate(h.labels):
            labels[mod][lab] += 1
            rates[mod][round(h.fs(i), 3)] += 1
            units[mod][h.units[i]] += 1
        if mod == "eeg":
            s = re.search(r"sub-[A-Za-z0-9]+", str(p)).group(0)
            hours_by_subject[s] += h.duration_s / 3600
            times["00:00:00" if h.start_seconds_of_day() == 0 else "other"] += 1

    # annotation files: column names and event categories only
    tsvs = sorted(p for p in files if p.name.endswith("_events.tsv"))
    columns, categories = Counter(), Counter()
    seizure_rows, subjects_with_sz = 0, Counter()
    for p in tsvs:
        with open(p, newline="") as fh:
            rows = list(csv.DictReader(fh, delimiter="\t"))
        if not rows:
            continue
        columns[tuple(rows[0].keys())] += 1
        col = next((c for c in ("eventType", "trial_type", "event_type", "type") if c in rows[0]), None)
        if col is None:
            continue
        s = re.search(r"sub-[A-Za-z0-9]+", str(p)).group(0)
        for r in rows:
            v = (r[col] or "").strip()
            categories[v] += 1
            if v.lower() not in NON_SEIZURE:
                seizure_rows += 1
                subjects_with_sz[s] += 1
    n_two = sum(1 for c in subjects_with_sz.values() if c >= 2)

    out = REPO / "results" / "lockbox"
    out.mkdir(parents=True, exist_ok=True)
    L = ["# SeizeIT2 blind feasibility audit", "",
         f"Generated {datetime.now().isoformat(timespec='seconds')} with `scripts/audit_seizeit2.py`. "
         "Only file listings, EDF headers and annotation column names and categories were read. No EEG samples were "
         "read, no seizure timings were looked at, and seizure numbers are totals across the whole dataset "
         "(docs/evaluation_methods.md v1.7, Section 12).", "",
         "## Files", "",
         f"- Subjects: {len(subjects)}; subject-sessions: {len(sessions)}; files: {len(files)}",
         "- By type: " + ", ".join(f"{k or '(none)'} {v}" for k, v in by_ext.most_common()),
         f"- EDF files readable: {sum(n_ok.values())} of {len(edfs)}"
         + (f"; unreadable: {len(bad)}" if bad else ""), "",
         "## Recordings by modality", "",
         "| Modality | EDF files | Hours | Channel labels (files) | Sampling rates, Hz (channels) | Units |",
         "|---|---|---|---|---|---|"]
    for mod in sorted(n_ok):
        L.append(f"| {mod} | {n_ok[mod]} | {hours[mod]:.0f} | "
                 + "; ".join(f"{k} ({v})" for k, v in labels[mod].most_common(12)) + " | "
                 + "; ".join(f"{k} ({v})" for k, v in rates[mod].most_common(5)) + " | "
                 + "; ".join(f"{k} ({v})" for k, v in units[mod].most_common(4)) + " |")
    eeg_h = sorted(hours_by_subject.values())
    L += ["", "## EEG timing", "",
          f"- EEG files starting at exactly 00:00:00: {times['00:00:00']}; other start times: {times['other']} "
          "(many 00:00:00 starts would suggest anonymized clock times, as in TUSZ)",
          (f"- EEG hours per subject: median {eeg_h[len(eeg_h) // 2]:.0f}, range {eeg_h[0]:.0f}–{eeg_h[-1]:.0f}"
           if eeg_h else "- no EEG hours found"), "",
          "## Annotations (totals only)", "",
          f"- Event files: {len(tsvs)}",
          "- Column sets: " + "; ".join(f"{', '.join(k)} ({v} files)" for k, v in columns.most_common(3)),
          "- Event categories: " + "; ".join(f"{k or '(blank)'} ({v})" for k, v in categories.most_common(15)),
          f"- Seizure events in total: {seizure_rows}; subjects with at least one: {len(subjects_with_sz)}; "
          f"with at least two (needed for the patient-specific design): {n_two}"]
    if bad:
        L += ["", "## Unreadable files", ""] + [f"- {b}" for b in bad[:50]]
    (out / "seizeit2_feasibility.md").write_text("\n".join(L) + "\n")

    print()
    print(f"Subjects {len(subjects)}, EDF files readable {sum(n_ok.values())}/{len(edfs)}")
    for mod in sorted(n_ok):
        print(f"  {mod}: {n_ok[mod]} files, {hours[mod]:.0f} h, channels {', '.join(list(labels[mod])[:6])}")
    print(f"EEG files starting at 00:00:00: {times['00:00:00']} of {sum(times.values())}")
    print(f"Seizure events (total): {seizure_rows}; subjects with >= 2: {n_two}")
    print(f"Report: {out / 'seizeit2_feasibility.md'}")


if __name__ == "__main__":
    main()

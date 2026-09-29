"""Blind feasibility audit of the SeizeIT2 lockbox (docs/evaluation_methods.md v1.7, Section 12).

Checks that SeizeIT2 can be used, without looking at anything that could shape the
design: it reads only file listings, EDF headers (channel names, sampling rates,
durations, start times) and the column names and event categories of the annotation
files. It never prints seizure timings, never reads EEG samples, and reports seizure
numbers only as totals across the whole dataset. Since v1.8 it also reads the recording
start times in the BIDS scans.tsv files, to see whether consecutive recordings can be
placed on one timeline (recording timing only; nothing about seizures). Since v1.9 it
also reads the dateTime and recordingDuration columns of the annotation files. It uses them
only if every row of a file carries the same dateTime (so it's the recording's start, not an
event's), and it reports only totals and the gaps between consecutive recordings.

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

    # recording timing (v1.8): scans.tsv start times and the gaps between consecutive EEG recordings
    eeg_dur, eeg_dur_by_stem = {}, {}
    for p in edfs:
        if modality(p) == "eeg":
            try:
                eeg_dur[p.name] = read_header(p).duration_s
                eeg_dur_by_stem[p.name[:-len("_eeg.edf")] if p.name.endswith("_eeg.edf") else p.stem] = (
                    eeg_dur[p.name], p)
            except Exception:  # noqa: BLE001
                pass
    scans = sorted(p for p in files if p.name.endswith("_scans.tsv"))
    scan_cols, gaps, midnight, n_times = Counter(), [], 0, 0
    for p in scans:
        with open(p, newline="") as fh:
            rows = list(csv.DictReader(fh, delimiter="\t"))
        if not rows:
            continue
        scan_cols[tuple(rows[0].keys())] += 1
        if "acq_time" not in rows[0]:
            continue
        seq = []
        for r in rows:
            name = Path(r.get("filename", "")).name
            if name not in eeg_dur:
                continue
            try:
                at = datetime.fromisoformat(r["acq_time"].replace("Z", ""))
            except ValueError:
                continue
            n_times += 1
            midnight += at.hour == 0 and at.minute == 0 and at.second == 0
            seq.append((at, eeg_dur[name]))
        seq.sort()
        for (a, d), (b, _) in zip(seq, seq[1:]):
            gaps.append((b - a).total_seconds() - d)

    # recording timing (v1.9): dateTime / recordingDuration in the annotation files
    ev_single, ev_multi, ev_midnight, dur_agree, dur_checked = 0, 0, 0, 0, 0
    starts_by_session = defaultdict(list)
    for p in tsvs:
        with open(p, newline="") as fh:
            rows = list(csv.DictReader(fh, delimiter="\t"))
        if not rows or "dateTime" not in rows[0]:
            continue
        values = {(r.get("dateTime") or "").strip() for r in rows}
        if len(values) != 1:
            ev_multi += 1                      # event-level times: not used, not printed
            continue
        try:
            start = datetime.fromisoformat(values.pop().replace("Z", ""))
        except ValueError:
            ev_multi += 1
            continue
        ev_single += 1
        ev_midnight += start.hour == 0 and start.minute == 0 and start.second == 0
        stem = p.name[:-len("_events.tsv")]
        dur = eeg_dur_by_stem.get(stem, (None, None))[0]
        try:
            rec_dur = float(rows[0].get("recordingDuration") or "nan")
        except ValueError:
            rec_dur = float("nan")
        if dur is not None and rec_dur == rec_dur:
            dur_checked += 1
            dur_agree += abs(rec_dur - dur) <= 2
        length = dur if dur is not None else rec_dur
        m1, m2 = re.search(r"sub-[A-Za-z0-9]+", str(p)), re.search(r"ses-[A-Za-z0-9]+", str(p))
        starts_by_session[(m1.group(0) if m1 else "", m2.group(0) if m2 else "")].append((start, length))
    ev_gaps = []
    for seq in starts_by_session.values():
        seq.sort()
        for (a, d), (b, _) in zip(seq, seq[1:]):
            if d == d:
                ev_gaps.append((b - a).total_seconds() - d)

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
          f"with at least two (needed for the patient-specific design): {n_two}",
          "", "## Recording timing (v1.8; recording start times only)", "",
          f"- scans.tsv files: {len(scans)}; column sets: "
          + "; ".join(f"{', '.join(k)} ({v})" for k, v in scan_cols.most_common(3)),
          f"- EEG recordings with an acq_time: {n_times}; of those at exactly midnight: {midnight}"]
    L += ["", "## Recording timing from the annotation files (v1.9; recording start times only)", "",
          f"- Annotation files with one dateTime for every row (a recording start): {ev_single}; "
          f"with differing dateTimes (event-level, not used): {ev_multi}",
          f"- Of the recording starts, at exactly midnight: {ev_midnight}",
          f"- recordingDuration matches the EDF duration within 2 s: {dur_agree} of {dur_checked}"]
    if ev_gaps:
        g = sorted(ev_gaps)
        within = sum(abs(x) <= 60 for x in g)
        L += [f"- Gaps between consecutive recordings in a session (next start minus previous end): {len(g)} gaps, "
              f"median {g[len(g) // 2]:.0f} s, within ±60 s: {within} ({100 * within / len(g):.0f}%), "
              f"overlaps over 60 s: {sum(x < -60 for x in g)}, gaps over 1 h: {sum(x > 3600 for x in g)}"]
    if gaps:
        g = sorted(gaps)
        within = sum(abs(x) <= 60 for x in g)
        L += [f"- Gaps between consecutive EEG recordings in a session (next start minus previous end): "
              f"{len(g)} gaps, median {g[len(g) // 2]:.0f} s, within ±60 s: {within} ({100 * within / len(g):.0f}%), "
              f"negative (overlap > 60 s): {sum(x < -60 for x in g)}, longer than 1 h: {sum(x > 3600 for x in g)}"]
    if bad:
        L += ["", "## Unreadable files", ""] + [f"- {b}" for b in bad[:50]]
    (out / "seizeit2_feasibility.md").write_text("\n".join(L) + "\n")

    print()
    print(f"Subjects {len(subjects)}, EDF files readable {sum(n_ok.values())}/{len(edfs)}")
    for mod in sorted(n_ok):
        print(f"  {mod}: {n_ok[mod]} files, {hours[mod]:.0f} h, channels {', '.join(list(labels[mod])[:6])}")
    print(f"EEG files starting at 00:00:00: {times['00:00:00']} of {sum(times.values())}")
    print(f"Seizure events (total): {seizure_rows}; subjects with >= 2: {n_two}")
    print(f"scans.tsv files: {len(scans)}; EEG recordings with acq_time: {n_times} (at midnight: {midnight})")
    if gaps:
        g = sorted(gaps)
        print(f"Gaps between consecutive EEG recordings: median {g[len(g) // 2]:.0f} s, "
              f"within ±60 s {100 * sum(abs(x) <= 60 for x in g) / len(g):.0f}%")
    print(f"Annotation dateTime: {ev_single} files with one recording start, {ev_multi} with event-level times; "
          f"at midnight: {ev_midnight}; recordingDuration matches EDF: {dur_agree}/{dur_checked}")
    if ev_gaps:
        g = sorted(ev_gaps)
        print(f"Gaps between consecutive recordings: {len(g)} gaps, median {g[len(g) // 2]:.0f} s, "
              f"within ±60 s {100 * sum(abs(x) <= 60 for x in g) / len(g):.0f}%, "
              f"overlaps > 60 s {sum(x < -60 for x in g)}, gaps > 1 h {sum(x > 3600 for x in g)}")
    print(f"Report: {out / 'seizeit2_feasibility.md'}")


if __name__ == "__main__":
    main()

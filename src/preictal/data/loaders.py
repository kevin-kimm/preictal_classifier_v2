"""Dataset readers for Siena, CHB-MIT, TUSZ, TUAR and mental arithmetic (REQ-H1, REQ-H3).

discover() lists every EDF recording with its seizure annotations in seconds
from the start of the recording. load() returns the harmonized signal.

Annotation sources:
    CHB-MIT     chbXX-summary.txt (seconds from file start)
    Siena       Seizures-list-PNxx.txt (wall-clock times, converted using the
                EDF header start time; any disagreement with the list's own
                "registration start time" is reported)
    TUSZ        .csv_bi files (seconds from file start)
    TUAR        _seiz.csv files (seconds from file start)
    Mental ar.  no seizures

Corrections to the datasets' own annotations are listed, with reasons, in
configs/annotation_corrections.yaml. The raw files are never edited; discover()
applies each correction and logs it.

Subject IDs are prefixed by source so IDs can't collide across datasets
(VT-08). TUSZ and TUAR share the prefix "tuh:" because they come from the same
hospital archive and use the same patient IDs. CHB-MIT chb21 is the same person
as chb01, so both map to "chbmit:chb01".
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .edf import read_header
from .harmonize import HarmonizedRecording, harmonize

DATASET_PREFIX = {
    "chbmit": "chbmit_",
    "siena": "siena_",
    "tusz": "tusz_",
    "tuar": "tuar_",
    "mental_arith": "mental_arith_",
}
TUH_NAME = re.compile(r"^([a-z]{8})_(s\d{3})_(t\d{3})")
CLOCK = re.compile(r"(\d{1,2})\s*[.:]\s*(\d{2})\s*[.:]\s*(\d{2})")
DEFAULT_CORRECTIONS = Path(__file__).resolve().parents[3] / "configs" / "annotation_corrections.yaml"


@dataclass
class Recording:
    dataset: str
    path: Path
    rel_path: str                       # relative to data/raw
    patient: str
    subject: str                        # grouping ID for cross-patient splits
    seizures: list[tuple[float, float]] = field(default_factory=list)  # (onset_s, offset_s)
    notes: list[str] = field(default_factory=list)
    excluded: list[tuple[float, float, str]] = field(default_factory=list)  # removed by corrections
    flags: list[dict] = field(default_factory=list)  # seizures to review by eye


# ---------------------------------------------------------------- helpers

def dataset_folders(data_root: Path) -> dict[str, Path]:
    found = {}
    for folder in sorted(p for p in Path(data_root).iterdir() if p.is_dir()):
        for key, prefix in DATASET_PREFIX.items():
            if folder.name.startswith(prefix):
                found[key] = folder
    return found


def edf_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*")
                  if p.suffix.lower() == ".edf" and not any(x.startswith(".") for x in p.parts))


def read_tuh_csv(path: Path) -> list[dict]:
    with open(path, newline="", errors="replace") as f:
        lines = [x for x in f if x.strip() and not x.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


def tuh_seizures(path: Path) -> list[tuple[float, float]]:
    """Unique seizure intervals in a TUH annotation file (label other than background)."""
    events = set()
    for r in read_tuh_csv(path):
        label = (r.get("label") or "").strip().lower()
        if label and label != "bckg":
            events.add((float(r["start_time"]), float(r["stop_time"])))
    return sorted(events)


# ---------------------------------------------------------------- CHB-MIT

def chbmit_annotations(folder: Path) -> tuple[dict[str, list[tuple[float, float]]], list[str]]:
    """File name -> seizure intervals, from every chbXX-summary.txt."""
    starts, ends, notes = {}, {}, []
    for summary in sorted(folder.rglob("*-summary.txt")):
        current = None
        for line in summary.read_text(errors="replace").splitlines():
            m = re.match(r"\s*File Name:\s*(\S+)", line, re.I)
            if m:
                current = m.group(1)
                starts.setdefault(current, [])
                ends.setdefault(current, [])
                continue
            m = re.match(r"\s*Seizure\s*\d*\s*(Start|End) Time:\s*(\d+)", line, re.I)
            if m and current:
                (starts if m.group(1).lower() == "start" else ends)[current].append(float(m.group(2)))
    out = {}
    for name in starts:
        if len(starts[name]) != len(ends[name]):
            notes.append(f"{name}: {len(starts[name])} start times but {len(ends[name])} end times")
        out[name] = list(zip(starts[name], ends[name]))
    return out, notes


# ---------------------------------------------------------------- Siena

def parse_clock(text: str) -> int | None:
    """Seconds after midnight from a Siena time string.

    Handles '19.58.36', '21:51:02' and '16:13.23'. When a line gives both a
    clinical and an electrographic onset, the electrographic one is used.
    """
    parts = text.split(";")
    chosen = next((p for p in parts if "ELECTR" in p.upper()), parts[0])
    m = CLOCK.search(chosen) or CLOCK.search(text)
    if not m:
        return None
    h, mi, s = (int(g) for g in m.groups())
    return h * 3600 + mi * 60 + s


def seconds_after(t: int, t0: int) -> int:
    """Clock time t relative to t0, assuming t is within 24 h after t0."""
    d = t - t0
    return d + 86400 if d < 0 else d


def siena_blocks(list_file: Path) -> list[dict]:
    """One dict per seizure entry: file, start, end (clock seconds), raw text.

    The "File name:" line can come before or after the "Seizure n" heading, so
    each entry takes the most recent file name that appears before its start time.
    """
    blocks, block, last_file = [], None, None
    for line in list_file.read_text(errors="replace").splitlines():
        s = line.strip()
        if re.match(r"seizure\s+n\s*\d", s, re.I):
            block = {"file": last_file} if last_file else {}
            blocks.append(block)
            continue
        m = re.match(r"file\s*name\s*:\s*(\S+)", s, re.I)
        if m:
            last_file = m.group(1)
            if block is not None and "start" not in block:
                block["file"] = last_file
            continue
        if block is None:
            continue
        m = re.match(r"registration\s+start\s+time\s*:?(.*)", s, re.I)
        if m:
            block["registration_start"] = parse_clock(m.group(1))
            continue
        if re.match(r"registration", s, re.I):
            continue
        m = re.match(r"(seizure\s+)?start\s+time\s*:?(.*)", s, re.I)
        if m:
            block["start"], block["start_text"] = parse_clock(m.group(2)), m.group(2).strip()
            continue
        m = re.match(r"(seizure\s+)?end\s+time\s*:?(.*)", s, re.I)
        if m:
            block["end"], block["end_text"] = parse_clock(m.group(2)), m.group(2).strip()
    return blocks


def match_siena_file(name: str, edfs_by_name: dict[str, Path], patient_edfs: list[Path]):
    """Find the EDF a seizure list refers to, tolerating the typos found in VT-01."""
    key = name.lower()
    if key in edfs_by_name:
        return edfs_by_name[key], ""
    fixed = re.sub(r"^pno", "pn0", key)  # letter O typed for zero (PNO6)
    if fixed in edfs_by_name:
        return edfs_by_name[fixed], "letter O typed for zero"
    if len(patient_edfs) == 1:          # e.g. PN01.edf, PN11-.edf
        return patient_edfs[0], "only EDF for this patient"
    return None, ""


def clock_text(t: int) -> str:
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def siena_annotations(folder: Path, edfs: list[Path]) -> tuple[dict, list[str], dict]:
    """EDF path -> seizure intervals in seconds from recording start.

    Also returns flags: seizures whose list and EDF header disagree on the
    recording start time, with the timing implied by the list as an alternative.
    """
    by_name = {p.name.lower(): p for p in edfs}
    by_patient = {}
    for p in edfs:
        m = re.match(r"(PN\d+)", p.name, re.I)
        if m:
            by_patient.setdefault(m.group(1).upper(), []).append(p)
    out, notes, flags = {p: [] for p in edfs}, [], {p: [] for p in edfs}
    for lst in sorted(q for q in folder.rglob("*.txt") if q.name.lower().startswith("seizures-list")):
        pid = re.search(r"(PN\d+)", lst.name, re.I).group(1).upper()
        for n, b in enumerate(siena_blocks(lst), 1):
            where = f"{lst.name} entry {n}"
            listed = b.get("file") or ""
            edf, how = match_siena_file(listed, by_name, by_patient.get(pid, []))
            if edf is None:
                notes.append(f"{where}: no EDF matches '{listed or '(no file name given)'}'")
                continue
            if how:
                notes.append(f"{where}: '{listed or '(no file name given)'}' matched to "
                             f"{edf.name} ({how})")
            if b.get("start") is None or b.get("end") is None:
                notes.append(f"{where}: could not read start/end time")
                continue
            t0 = read_header(edf).start_seconds_of_day()
            if t0 is None:
                notes.append(f"{where}: unreadable EDF start time")
                continue
            onset, offset = seconds_after(b["start"], t0), seconds_after(b["end"], t0)
            reg = b.get("registration_start")
            if reg is not None and min(abs(reg - t0), 86400 - abs(reg - t0)) > 1:
                reason = (f"{where}: list gives registration start {clock_text(reg)} but the EDF "
                          f"header says {clock_text(t0)}; the EDF header time is used")
                notes.append(reason)
                flags[edf].append({"onset": float(onset), "offset": float(offset), "reason": reason,
                                   "alt": (float(seconds_after(b["start"], reg)),
                                           float(seconds_after(b["end"], reg))),
                                   "alt_label": "timing implied by the list's registration start"})
            if "ELECTR" in b.get("start_text", "").upper():
                notes.append(f"{where}: used electrographic onset ({b['start_text']})")
            out[edf].append((float(onset), float(offset)))
    return out, notes, flags


# ---------------------------------------------------------------- corrections

def load_corrections(path: Path = DEFAULT_CORRECTIONS) -> list[dict]:
    if not Path(path).exists():
        return []
    return yaml.safe_load(Path(path).read_text()) or []


def apply_corrections(recs: list[Recording], corrections: list[dict], notes: list[str]) -> None:
    """Apply annotation corrections in place.

    Seizure numbers are 1-based and refer to the recording's seizures in time
    order before any correction. A correction is skipped (and reported) if its
    recording isn't found, or if expected_onset_s doesn't match the annotation.
    """
    by_file = {}
    for r in recs:
        by_file.setdefault((r.dataset, r.path.name), []).append(r)
    pending = {}
    for c in corrections:
        where = f"{c.get('dataset')} {c.get('recording')} seizure {c.get('seizure')}"
        targets = by_file.get((c.get("dataset"), c.get("recording")), [])
        if len(targets) != 1:
            if c.get("dataset") in {r.dataset for r in recs}:
                notes.append(f"correction not applied, recording not found: {where}")
            continue
        rec, k = targets[0], int(c["seizure"]) - 1
        if not 0 <= k < len(rec.seizures):
            notes.append(f"correction not applied, no such seizure: {where}")
            continue
        expected = c.get("expected_onset_s")
        if expected is not None and abs(rec.seizures[k][0] - float(expected)) > 1:
            notes.append(f"correction not applied, onset {rec.seizures[k][0]} s does not match "
                         f"expected {expected} s: {where}")
            continue
        pending.setdefault(id(rec), (rec, {}))[1][k] = c

    for rec, actions in pending.values():
        kept = []
        for k, (on, off) in enumerate(rec.seizures):
            c = actions.get(k)
            if c is None:
                kept.append((on, off))
                continue
            reason = " ".join(str(c.get("reason", "")).split())
            action = c.get("action")
            where = f"{rec.dataset} {rec.path.name} seizure {k + 1}"
            if action == "exclude":
                rec.excluded.append((on, off, reason))
                notes.append(f"correction applied: {where} excluded ({reason})")
                continue
            if action in ("set_onset_s", "set_offset_s"):
                new = (float(c["value"]), off) if action == "set_onset_s" else (on, float(c["value"]))
                kept.append(new)
                rec.flags.append({"onset": new[0], "offset": new[1], "reason": f"corrected: {reason}",
                                  "alt": (on, off), "alt_label": "original annotation",
                                  "changed": "onset" if action == "set_onset_s" else "offset"})
                notes.append(f"correction applied: {where} {action} {c['value']} ({reason})")
                continue
            kept.append((on, off))
            notes.append(f"correction not applied, unknown action '{action}': {where}")
        rec.seizures = sorted(kept)


# ---------------------------------------------------------------- discover

def discover(data_root: str | Path, datasets=tuple(DATASET_PREFIX),
             notes: list[str] | None = None, corrections: list[dict] | None = None) -> list[Recording]:
    """All recordings in the requested datasets, with seizure annotations.

    Dataset-level notes (for example, corrected file names in the Siena lists)
    are appended to `notes` if a list is given. Annotation corrections come from
    configs/annotation_corrections.yaml unless a list is passed.
    """
    notes = notes if notes is not None else []
    corrections = load_corrections() if corrections is None else corrections
    data_root = Path(data_root)
    folders = dataset_folders(data_root)
    recs = []
    for key in datasets:
        folder = folders.get(key)
        if folder is None:
            continue
        edfs = edf_files(folder)
        if key == "chbmit":
            ann, n = chbmit_annotations(folder)
            notes += [f"chbmit: {x}" for x in n]
            for p in edfs:
                patient = re.match(r"(chb\d+)", p.name, re.I).group(1).lower()
                subject = "chb01" if patient == "chb21" else patient
                rec = Recording(key, p, str(p.relative_to(data_root)), patient, f"chbmit:{subject}")
                if p.name in ann:
                    rec.seizures = ann[p.name]
                else:
                    rec.notes.append("not listed in the summary file; assumed seizure-free")
                recs.append(rec)
        elif key == "siena":
            ann, n, siena_flags = siena_annotations(folder, edfs)
            notes += [f"siena: {x}" for x in n]
            for p in edfs:
                patient = re.match(r"(PN\d+)", p.name, re.I).group(1).upper()
                rec = Recording(key, p, str(p.relative_to(data_root)), patient, f"siena:{patient}",
                                seizures=sorted(ann.get(p, [])))
                rec.notes = [x for x in n if p.name in x]
                rec.flags = list(siena_flags.get(p, []))
                recs.append(rec)
        elif key in ("tusz", "tuar"):
            for p in edfs:
                m = TUH_NAME.match(p.name)
                patient = m.group(1) if m else ""
                rec = Recording(key, p, str(p.relative_to(data_root)), patient, f"tuh:{patient}")
                ann = p.with_suffix(".csv_bi") if key == "tusz" else p.with_name(p.stem + "_seiz.csv")
                if ann.exists():
                    rec.seizures = tuh_seizures(ann)
                elif key == "tusz":
                    rec.notes.append("no .csv_bi annotation file")
                recs.append(rec)
        elif key == "mental_arith":
            for p in edfs:
                m = re.match(r"(Subject\d+)", p.name, re.I)
                patient = m.group(1) if m else p.stem
                recs.append(Recording(key, p, str(p.relative_to(data_root)), patient,
                                      f"mental_arith:{patient}"))
    apply_corrections(recs, corrections, notes)
    return recs


def load(rec: Recording) -> HarmonizedRecording:
    """Harmonized signal for one recording."""
    return harmonize(read_header(rec.path))

"""Relabeling (REQ-L1, REQ-L2).

Labels every moment of every recording as preictal, ictal, interictal or
excluded, following docs/verification_plan.md, Section 3 and decision D-5.

Labels are computed on a *timeline*: the recordings of one patient (one TUSZ
session) placed in time order, so a seizure early in one file can have its
preictal period in the previous file, and the 4 h interictal rule sees
seizures in neighbouring files. Windows are cut afterwards and labeled by their
end time, so the window length and step can change without relabeling.

Rules (defaults from configs/default.yaml):
    event        seizures starting < 30 min after the previous one ends are merged
    eligible     at least 90% of the event's preictal period is recorded
    preictal     onset - 30 min <= t <= onset - 5 s, eligible events only
    ictal        onset <= t <= offset, every annotated seizure
    interictal   at least 4 h from every seizure onset and offset on the timeline,
                 including seizures excluded by annotation corrections (F-11)
    excluded     everything else (the 5 s gap, ineligible preictal periods, 30 min
                 to 4 h around seizures, ...)

Timeline placement uses each EDF header's start time of day. Recordings are
taken in file-name order; a recording that starts earlier in the day than the
previous one ended (by more than an hour) is placed on the next day. This errs
towards shorter gaps, which can only make fewer windows interictal. A recording
without a readable start time can't be placed: it is labeled on its own, and
none of its time is interictal if its patient (or TUSZ session) has seizures.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

from ..config import load_config
from .edf import read_header
from .loaders import Recording

PREICTAL, ICTAL, INTERICTAL, EXCLUDED = 0, 1, 2, 3
LABEL_NAMES = ("preictal", "ictal", "interictal", "excluded")
DAY = 86400.0
MAX_OVERLAP_S = 3600.0   # a start up to 1 h before the previous end is an overlap, not the next day


@dataclass(frozen=True)
class LabelRules:
    preictal_start_s: float = 1800.0
    sph_s: float = 5.0
    interictal_gap_s: float = 4 * 3600.0
    merge_gap_s: float = 1800.0
    min_coverage: float = 0.9

    @classmethod
    def from_config(cls, cfg: dict | None = None) -> "LabelRules":
        lab = (cfg or load_config())["labels"]
        return cls(preictal_start_s=lab["preictal_start_min_before_onset"] * 60.0,
                   sph_s=float(lab["preictal_end_s_before_onset"]),
                   interictal_gap_s=lab["interictal_min_gap_h"] * 3600.0,
                   merge_gap_s=lab["cluster_merge_min"] * 60.0,
                   min_coverage=float(lab["min_preictal_coverage"]))


@dataclass
class Placed:
    """A recording placed on a timeline (times in seconds on that timeline)."""
    rec: Recording
    start: float
    duration: float
    anchored: bool = True

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass
class Event:
    onset: float
    offset: float
    n_seizures: int
    coverage: float
    eligible: bool
    recording: str


@dataclass
class Timeline:
    key: tuple
    dataset: str
    subject: str
    role: str                                   # train_test | false_alarm_only
    placed: list[Placed]
    allow_interictal: bool = True
    seizures: list[tuple[float, float]] = field(default_factory=list)   # annotated, used
    blocking: list[tuple[float, float]] = field(default_factory=list)   # annotated + excluded
    events: list[Event] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- helpers

def natural_key(name: str) -> list:
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", name)]


def timeline_key(rec: Recording) -> tuple:
    if rec.dataset in ("tusz", "tuar"):
        m = re.match(r"^[a-z]{8}_(s\d{3})", rec.path.name)
        return (rec.dataset, rec.patient, m.group(1) if m else rec.path.name)
    if rec.dataset in ("chbmit", "siena"):
        return (rec.dataset, rec.patient)
    return (rec.dataset, rec.rel_path)       # e.g. mental arithmetic: each recording alone


def covered_length(a: float, b: float, spans: list[tuple[float, float]]) -> float:
    """Length of [a, b] covered by the union of spans."""
    pieces = sorted((max(a, s), min(b, e)) for s, e in spans if e > a and s < b)
    total, cur_s, cur_e = 0.0, None, None
    for s, e in pieces:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


def place(recs: list[Recording], info: dict[str, tuple[float | None, float]],
          notes: list[str]) -> list[Placed]:
    """Put recordings on one timeline using their start time of day (see module docstring)."""
    placed, prev_end = [], None
    for rec in sorted(recs, key=lambda r: natural_key(r.path.name)):
        t0, duration = info[rec.rel_path]
        if t0 is None:
            placed.append(Placed(rec, 0.0, duration, anchored=False))
            notes.append(f"{rec.rel_path}: no readable start time; labeled on its own")
            continue
        if prev_end is None:
            start = float(t0)
        else:
            start = math.floor(prev_end / DAY) * DAY + t0
            if start < prev_end - MAX_OVERLAP_S:
                start += DAY
            if start < prev_end:
                notes.append(f"{rec.rel_path}: overlaps the previous recording by {prev_end - start:.0f} s")
        placed.append(Placed(rec, start, duration))
        prev_end = start + duration if prev_end is None else max(prev_end, start + duration)
    return placed


def make_events(seizures: list[tuple[float, float]], spans: list[tuple[float, float]],
                where: dict[float, str], rules: LabelRules) -> list[Event]:
    events = []
    for on, off in sorted(seizures):
        if events and on - events[-1].offset < rules.merge_gap_s:
            ev = events[-1]
            ev.offset, ev.n_seizures = max(ev.offset, off), ev.n_seizures + 1
            continue
        a, b = on - rules.preictal_start_s, on - rules.sph_s
        cov = covered_length(a, b, spans) / (b - a)
        events.append(Event(on, off, 1, cov, cov >= rules.min_coverage, where.get(on, "")))
    return events


# ---------------------------------------------------------------- timelines

def build_timelines(recs: list[Recording], rules: LabelRules | None = None,
                    info: dict[str, tuple[float | None, float]] | None = None) -> list[Timeline]:
    """Group recordings into timelines and find their seizure events.

    info maps rel_path -> (start time of day in seconds or None, duration in seconds).
    If not given, it is read from the EDF headers.
    """
    rules = rules or LabelRules.from_config()
    recs = [r for r in recs if r.dataset != "tuar"]   # TUAR is for artifact tests, not labels
    if info is None:
        info = {}
        for r in recs:
            h = read_header(r.path)
            info[r.rel_path] = (h.start_seconds_of_day(), h.duration_s)

    seizure_patients = {(r.dataset, r.patient) for r in recs if r.seizures or r.excluded}
    groups = {}
    for r in recs:
        groups.setdefault(timeline_key(r), []).append(r)

    timelines = []
    for key, group in sorted(groups.items()):
        ds = group[0].dataset
        if ds == "mental_arith" or (ds == "tusz" and (ds, group[0].patient) not in seizure_patients):
            role = "false_alarm_only"
        else:
            role = "train_test"
        group_has_seizures = any(r.seizures or r.excluded for r in group)
        notes = []
        placed = place(group, info, notes)
        anchored = [p for p in placed if p.anchored]
        pieces = [(key, anchored, True)] if anchored else []
        # unanchored recordings: labeled alone; no interictal if the group has seizures
        pieces += [(key + (p.rec.rel_path,), [p], not group_has_seizures)
                   for p in placed if not p.anchored]
        for k, members, allow in pieces:
            tl = Timeline(k, ds, group[0].subject, role, members, allow_interictal=allow,
                          notes=list(notes) if members is anchored else [])
            where = {}
            for p in members:
                for on, off in p.rec.seizures:
                    tl.seizures.append((p.start + on, p.start + off))
                    where[p.start + on] = p.rec.rel_path
                for on, off, _ in p.rec.excluded:
                    tl.blocking.append((p.start + on, p.start + off))
            tl.blocking += tl.seizures
            spans = [(p.start, p.end) for p in members]
            tl.events = make_events(tl.seizures, spans, where, rules)
            timelines.append(tl)
    return timelines


# ---------------------------------------------------------------- labels

def labels_at(t: np.ndarray, tl: Timeline, rules: LabelRules) -> np.ndarray:
    """Label for each time t (seconds on the timeline)."""
    t = np.asarray(t, dtype=float)
    lab = np.full(t.shape, EXCLUDED, dtype=np.int8)
    if tl.allow_interictal:
        far = np.ones(t.shape, dtype=bool)
        for on, off in tl.blocking:
            far &= (t <= on - rules.interictal_gap_s) | (t >= off + rules.interictal_gap_s)
        lab[far] = INTERICTAL
    for ev in tl.events:
        if ev.eligible:
            lab[(t >= ev.onset - rules.preictal_start_s) & (t <= ev.onset - rules.sph_s)] = PREICTAL
    for on, off in tl.seizures:
        lab[(t >= on) & (t <= off)] = ICTAL
    return lab


def label_intervals(p: Placed, tl: Timeline, rules: LabelRules) -> list[tuple[float, float, str]]:
    """Label intervals for one recording, in seconds from the recording's start."""
    cuts = {p.start, p.end}
    g, pre, sph = rules.interictal_gap_s, rules.preictal_start_s, rules.sph_s
    for on, off in tl.blocking:
        cuts.update((on - g, off + g, on, off))
    for ev in tl.events:
        cuts.update((ev.onset - pre, ev.onset - sph, ev.onset))
    cuts = sorted(c for c in cuts if p.start <= c <= p.end)
    if len(cuts) < 2:
        return []
    mids = np.array([(a + b) / 2 for a, b in zip(cuts, cuts[1:])])
    labs = labels_at(mids, tl, rules)
    out = []
    for (a, b), lab in zip(zip(cuts, cuts[1:]), labs):
        name = LABEL_NAMES[lab]
        if out and out[-1][2] == name:
            out[-1] = (out[-1][0], b - p.start, name)
        else:
            out.append((a - p.start, b - p.start, name))
    return out


def window_labels(p: Placed, tl: Timeline, rules: LabelRules, length_s: float, step_s: float):
    """Window start times (seconds from recording start) and labels, labeled by end time."""
    if p.duration < length_s:
        return np.array([]), np.array([], dtype=np.int8)
    starts = np.arange(0.0, p.duration - length_s + 1e-9, step_s)
    return starts, labels_at(p.start + starts + length_s, tl, rules)

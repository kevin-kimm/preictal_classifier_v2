"""SeizeIT2 adapter (docs/evaluation_methods.md v1.13 Section 11.5, and v1.15).

Technical adapter only; the design is frozen. It implements the frozen rules for SeizeIT2:

* channels: the behind-the-ear EEG channels present (BTEleft SD, BTEright SD, CROSStop SD),
  resampled to 256 Hz, act as the "derivations"; BTEleft/BTEright are the homologous pair;
* seizures: annotation rows whose eventType starts with "sz" (onset and duration);
* timeline: clock times are anonymized, so each patient's files are placed back to back in
  (session, run) order. Distances for the 4 h interictal rule are measured on that timeline
  (real breaks can only make true distances longer). Preictal windows come only from the
  seizure's own file, and the 90% coverage rule is applied within that file.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..features.build_features import (
    CONNECTIVITY_FEATURES, FEATURES_V2, connectivity_features, window_features,
)
from .edf import read_header, read_signals
from .harmonize import TARGET_FS, microvolt_factor, resample
from .labels import (
    EXCLUDED, PREICTAL, Event, LabelRules, Placed, Timeline, covered_length, labels_at, make_events,
)
from .loaders import Recording

CHANNELS = ("BTEleft SD", "BTEright SD", "CROSStop SD")
FEATURE_CODE, VERSION_TEXT = "d2-v2-bte", "seizeit2 adapter"      # feature version inputs
HOMOLOGOUS_BTE = [("BTEleft SD", "BTEright SD")]


@dataclass
class Patient:
    subject: str                      # "seizeit2:sub-001"
    recordings: list[Recording]       # in (session, run) order
    durations: list[float]
    notes: list[str] = field(default_factory=list)


def _order_key(path: Path):
    ses = re.search(r"ses-(\w+?)_", path.name)
    run = re.search(r"run-(\d+)", path.name)
    return (ses.group(1) if ses else "", int(run.group(1)) if run else 0)


def read_seizures(events_tsv: Path) -> list[tuple[float, float]]:
    """(onset, offset) in seconds from the file's start, for rows whose eventType starts with 'sz'."""
    if not events_tsv.exists():
        return []
    out = []
    with open(events_tsv, newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if (r.get("eventType") or "").strip().lower().startswith("sz"):
                on = float(r["onset"])
                out.append((on, on + float(r["duration"])))
    return sorted(out)


def discover_patient(root: Path, sub: str) -> Patient:
    """The EEG recordings of one SeizeIT2 subject (e.g. 'sub-001'), in session and run order."""
    edfs = sorted((root / sub).glob("ses-*/eeg/*_eeg.edf"), key=_order_key)
    recs, durs, notes = [], [], []
    for p in edfs:
        hdr = read_header(p)
        seizures = read_seizures(p.with_name(p.name[: -len("_eeg.edf")] + "_events.tsv"))
        recs.append(Recording("seizeit2", p, str(p.relative_to(root.parent)), sub, f"seizeit2:{sub}", seizures))
        durs.append(float(hdr.duration_s))
    if not edfs:
        notes.append(f"{sub}: no EEG files")
    return Patient(f"seizeit2:{sub}", recs, durs, notes)


def timeline(patient: Patient, rules: LabelRules) -> Timeline:
    """Files back to back in run order; events with the coverage rule applied within the onset's file."""
    placed, spans, seizures, where, t = [], [], [], {}, 0.0
    for rec, dur in zip(patient.recordings, patient.durations):
        placed.append(Placed(rec, t, dur))
        spans.append((t, t + dur))
        for on, off in rec.seizures:
            seizures.append((t + on, t + off))
            where[t + on] = rec.rel_path
        t += dur
    events = make_events(seizures, spans, where, rules)
    fixed = []
    for ev in events:
        own = [s for s in spans if s[0] <= ev.onset < s[1]]         # the file the onset is in
        a, b = ev.onset - rules.preictal_start_s, ev.onset - rules.sph_s
        cov = covered_length(a, b, own) / (b - a) if own else 0.0
        fixed.append(Event(ev.onset, ev.offset, ev.n_seizures, cov, cov >= rules.min_coverage, ev.recording))
    tl = Timeline(("seizeit2", patient.subject.split(":")[1]), "seizeit2", patient.subject, "train_test", placed)
    tl.seizures = sorted(seizures)
    tl.blocking = sorted(seizures)
    tl.events = fixed
    return tl


def window_labels(p: Placed, tl: Timeline, rules: LabelRules, length_s: float, step_s: float):
    """Window starts (s from the file's start) and labels; preictal only from the seizure's own file."""
    if p.duration < length_s:
        return np.array([]), np.array([], dtype=np.int8)
    starts = np.arange(0.0, p.duration - length_s + 1e-9, step_s)
    t_end = p.start + starts + length_s
    lab = labels_at(t_end, tl, rules)
    same_file = np.zeros(len(starts), dtype=bool)
    for ev in tl.events:
        if ev.eligible and p.start <= ev.onset < p.end:
            same_file |= (t_end >= ev.onset - rules.preictal_start_s) & (t_end <= ev.onset - rules.sph_s)
    lab[(lab == PREICTAL) & ~same_file] = EXCLUDED
    return starts, lab


def read_bte(path: Path, first_record: int = 0, n_records: int | None = None):
    """The behind-the-ear channels in µV (3 x n, NaN rows where absent), at the file's own rate."""
    hdr = read_header(path)
    idx = [hdr.labels.index(c) if c in hdr.labels else None for c in CHANNELS]
    present = np.array([i is not None for i in idx])
    got = read_signals(hdr, [i for i in idx if i is not None], first_record, n_records)
    fs_in = {hdr.fs(i) for i in idx if i is not None}
    if len(fs_in) > 1:
        raise ValueError(f"{path.name}: behind-the-ear channels have different sampling rates {fs_in}")
    n = len(got[0]) if got else 0
    out = np.full((len(CHANNELS), n), np.nan)
    k = 0
    for j, i in enumerate(idx):
        if i is not None:
            f = microvolt_factor(hdr.units[i])
            out[j] = got[k] * (1.0 if f is None else f)
            k += 1
    return out, present, (fs_in.pop() if fs_in else float("nan")), hdr


def recording_features(path: Path, starts_s: np.ndarray, length_s: float, chunk_windows: int = 720,
                       warmup_s: float = 10.0, pad_s: float = 2.0):
    """Feature set v2 for SeizeIT2: per-channel (n x 3 x 19), connectivity (n x 12), presence flags."""
    hdr = read_header(path)
    starts_s = np.asarray(starts_s, dtype=float)
    feats = np.full((len(starts_s), len(CHANNELS), len(FEATURES_V2)), np.nan, dtype=np.float32)
    conn = np.full((len(starts_s), len(CONNECTIVITY_FEATURES)), np.nan, dtype=np.float32)
    present = np.zeros(len(CHANNELS), dtype=bool)
    rs = hdr.record_s
    for k0 in range(0, len(starts_s), chunk_windows):
        chunk = starts_s[k0:k0 + chunk_windows]
        lead = float(np.floor(min(warmup_s, chunk[0])))
        want0, want1 = chunk[0] - lead, min(chunk[-1] + length_s, hdr.duration_s)
        a, b = max(0.0, want0 - pad_s), min(hdr.duration_s, want1 + pad_s)
        r0, r1 = int(math.floor(a / rs)), min(hdr.n_records, int(math.ceil(b / rs)))
        raw, present, fs_in, _ = read_bte(path, r0, r1 - r0)
        x = np.full((len(CHANNELS), int(round((r1 - r0) * rs * TARGET_FS)) + 2), np.nan)
        n = None
        for j in range(len(CHANNELS)):
            if present[j]:
                y = resample(raw[j], fs_in, TARGET_FS)
                n = len(y) if n is None else min(n, len(y))
                x[j, :len(y)] = y
        x = x[:, :n] if n else x
        i0 = int(round((want0 - r0 * rs) * TARGET_FS))
        x = x[:, i0:i0 + int(round((want1 - want0) * TARGET_FS))]
        idx = np.round((chunk - want0) * TARGET_FS).astype(int)
        length = int(round(length_s * TARGET_FS))
        ok = idx + length <= x.shape[1]
        if ok.any():
            feats[k0:k0 + len(chunk)][ok] = window_features(x, present, TARGET_FS, idx[ok], length, extra=True)
            conn[k0:k0 + len(chunk)][ok] = connectivity_features(x, present, TARGET_FS, idx[ok], length,
                                                                 channel_names=CHANNELS, homologous=HOMOLOGOUS_BTE)
    return feats, conn, present


def cohort(repo: Path, group: str, lockbox_run: bool = False):
    """Who is tested and who trains the general part, for a SeizeIT2 run (evaluation methods v1.15).

    development: test the 25 development patients; the general part uses the other development
    patients only, so the lockbox stays untouched. lockbox: test the 100 lockbox patients; the
    general part uses all other SeizeIT2 patients. Refused unless lockbox_run is set and the
    freeze-v1.13 Git tag exists. Returns (subject info dict, test subjects, training pool).
    """
    import subprocess

    import yaml

    from ..evaluation.lopo import SubjectInfo
    split = yaml.safe_load((repo / "configs" / "seizeit2_split.yaml").read_text())
    if group == "lockbox":
        tags = subprocess.run(["git", "tag", "-l", "freeze-v1.13"], cwd=repo, capture_output=True, text=True).stdout
        if not lockbox_run or "freeze-v1.13" not in tags:
            raise SystemExit("Refusing to touch the lockbox: it is opened only for the single lockbox run, after the "
                             "freeze (needs --lockbox-run and the freeze-v1.13 Git tag).")
    dev = {f"seizeit2:{s}" for s in split["development"]}
    test = {f"seizeit2:{s}" for s in split[group]}
    pool = test | dev if group == "lockbox" else dev
    info = {s: SubjectInfo("seizeit2", "train_test", False) for s in pool}
    return info, test, pool


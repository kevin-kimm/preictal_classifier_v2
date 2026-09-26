"""Signal harmonization (REQ-H1, REQ-H2, REQ-H4).

Turns an EDF recording from any of the datasets into one format:

* the 18-derivation bipolar longitudinal montage (decision D-4), with modern
  10-20 names (T3->T7, T4->T8, T5->P7, T6->P8),
* microvolts,
* 256 Hz.

Referential recordings (Siena, TUSZ, TUAR, mental arithmetic, and a few
CHB-MIT files) are converted by subtracting electrode pairs, which cancels the
reference. Bipolar recordings (most of CHB-MIT) are used directly. A derivation
whose electrodes are missing is marked absent (NaN row, present=False); it is
never interpolated.

Every channel in the file ends up in the channel log as either used or
excluded with a reason, so nothing is dropped silently.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
from scipy.signal import resample_poly

from .edf import EDFHeader, read_signals

TARGET_FS = 256

MONTAGE = (
    ("Fp1", "F7"), ("F7", "T7"), ("T7", "P7"), ("P7", "O1"),   # left temporal
    ("Fp2", "F8"), ("F8", "T8"), ("T8", "P8"), ("P8", "O2"),   # right temporal
    ("Fp1", "F3"), ("F3", "C3"), ("C3", "P3"), ("P3", "O1"),   # left parasagittal
    ("Fp2", "F4"), ("F4", "C4"), ("C4", "P4"), ("P4", "O2"),   # right parasagittal
    ("Fz", "Cz"), ("Cz", "Pz"),                                # midline
)
DERIVATIONS = tuple(f"{a}-{b}" for a, b in MONTAGE)

MONTAGE_ELECTRODES = {e for pair in MONTAGE for e in pair}
# Real electrode positions that appear in the datasets but are not in the montage.
OTHER_ELECTRODES = {
    "Fpz", "Oz", "F1", "F2", "F5", "F6", "F9", "F10", "AF3", "AF4", "AF7", "AF8",
    "FC1", "FC2", "FC3", "FC4", "FC5", "FC6", "FCz", "FT7", "FT8", "FT9", "FT10",
    "C1", "C2", "C5", "C6", "CP1", "CP2", "CP3", "CP4", "CP5", "CP6", "CPz",
    "TP7", "TP8", "TP9", "TP10", "P1", "P2", "P5", "P6", "P9", "P10",
    "PO3", "PO4", "PO7", "PO8", "POz",
    "A1", "A2", "M1", "M2",                    # ear / mastoid
    "T1", "T2", "SP1", "SP2", "PG1", "PG2",    # anterior temporal, sphenoidal, nasopharyngeal
    "C3P", "C4P",                              # TUH-specific extra electrodes
}
CANONICAL = {name.upper(): name for name in MONTAGE_ELECTRODES | OTHER_ELECTRODES}
OLD_NAMES = {"T3": "T7", "T4": "T8", "T5": "P7", "T6": "P8"}
DIGIT_TYPOS = {"01": "O1", "02": "O2"}  # CHB-MIT writes O1 as "01" in some files
REFERENCE_TOKENS = {"REF", "LE", "CS2", "AR", "AVG"}
NON_EEG_WORDS = {
    "ECG", "EKG", "EKG1", "EKG2", "EMG", "EOG", "CHIN", "LOC", "ROC", "LUC", "RLC",
    "LUE", "RAE", "VNS", "RESP", "RESP1", "RESP2", "ABDOMEN", "PHOTIC", "PH",
    "SPO2", "HR", "PLET", "MK", "SUPPR", "IBI", "BURSTS", "PULSE", "RATE",
}
PLACEHOLDERS = {"", "-", ".", "--"}


# ---------------------------------------------------------------- labels

@dataclass(frozen=True)
class Label:
    raw: str
    kind: str          # electrode | bipolar | non_eeg | numbered | placeholder | unrecognized
    a: str = ""        # electrode (referential) or first electrode (bipolar)
    b: str = ""        # second electrode (bipolar)
    ref: str = ""      # reference token for referential channels, e.g. REF, LE, CS2

    @property
    def canonical(self) -> str:
        if self.kind == "electrode":
            return self.a + (f" (ref {self.ref})" if self.ref else "")
        if self.kind == "bipolar":
            return f"{self.a}-{self.b}"
        return ""


def electrode_name(token: str) -> str | None:
    """Canonical modern name for an electrode token, or None."""
    t = token.strip().upper()
    t = DIGIT_TYPOS.get(t, t)
    t = OLD_NAMES.get(t, t)
    return CANONICAL.get(t)


def parse_label(raw: str) -> Label:
    """Classify one EDF channel label."""
    s = raw.strip()
    if s in PLACEHOLDERS:
        return Label(raw, "placeholder")
    u = s.upper()
    if u.startswith(("ECG ", "EKG ")):
        return Label(raw, "non_eeg")
    if u.startswith("EEG "):
        u = u[4:].strip()
    words = [w for w in re.split(r"[\s\-]+", u) if w]
    if any(w in NON_EEG_WORDS or re.fullmatch(r"DC\d+", w) for w in words):
        return Label(raw, "non_eeg")

    parts = [p.strip() for p in u.split("-")]
    ref = ""
    if len(parts) == 2 and parts[1] in REFERENCE_TOKENS:
        ref, parts = parts[1], parts[:1]
    if len(parts) == 1:
        e = electrode_name(parts[0])
        if e:
            return Label(raw, "electrode", a=e, ref=ref)
        if parts[0].isdigit():
            return Label(raw, "numbered")
        return Label(raw, "unrecognized")
    if len(parts) == 2:
        a, b = electrode_name(parts[0]), electrode_name(parts[1])
        if a and b:
            return Label(raw, "bipolar", a=a, b=b)
        if parts[0].isdigit() or parts[1].isdigit():
            return Label(raw, "numbered")
    return Label(raw, "unrecognized")


def looks_like_eeg(raw: str) -> bool:
    """True for labels that claim to be EEG; used to flag unmapped EEG channels (VT-02)."""
    return raw.strip().upper().startswith("EEG ")


# ---------------------------------------------------------------- montage plan

@dataclass
class MontagePlan:
    labels: list[Label]
    steps: list[tuple]   # per derivation: ("direct", i) | ("reversed", i) |
                         # ("referential", i, j) | ("absent", reason)
    channel_log: list[dict] = field(default_factory=list)

    @property
    def present(self) -> np.ndarray:
        return np.array([s[0] != "absent" for s in self.steps])

    @property
    def used_indices(self) -> list[int]:
        idx = set()
        for s in self.steps:
            if s[0] != "absent":
                idx.update(s[1:])
        return sorted(idx)

    def source(self, k: int) -> str:
        s = self.steps[k]
        if s[0] == "referential":
            return f"referential ({self.labels[s[1]].ref or 'no reference label'})"
        return s[0] if s[0] != "absent" else f"absent: {s[1]}"


EXCLUSION_REASONS = {
    "non_eeg": "excluded: non-EEG signal",
    "numbered": "excluded: numbered channel with no electrode position",
    "placeholder": "excluded: empty placeholder channel",
    "unrecognized": "unrecognized label",
}


def plan_montage(raw_labels: list[str]) -> MontagePlan:
    """Decide how to build each derivation from the channels in a file (no data is read)."""
    labels = [parse_label(x) for x in raw_labels]
    bipolar, electrodes, duplicates = {}, {}, set()
    for i, lab in enumerate(labels):
        if lab.kind == "bipolar":
            key = (lab.a, lab.b)
            if key in bipolar:
                duplicates.add(i)
            else:
                bipolar[key] = i
        elif lab.kind == "electrode":
            if lab.a in electrodes:
                duplicates.add(i)
            else:
                electrodes[lab.a] = i

    steps = []
    for a, b in MONTAGE:
        if (a, b) in bipolar:
            steps.append(("direct", bipolar[(a, b)]))
        elif (b, a) in bipolar:
            steps.append(("reversed", bipolar[(b, a)]))
        elif a in electrodes and b in electrodes:
            ia, ib = electrodes[a], electrodes[b]
            if labels[ia].ref == labels[ib].ref:
                steps.append(("referential", ia, ib))
            else:
                steps.append(("absent", f"{a} and {b} use different references"))
        else:
            missing = [e for e in (a, b) if e not in electrodes]
            steps.append(("absent", "missing " + ", ".join(missing)))

    plan = MontagePlan(labels=labels, steps=steps)
    used = set(plan.used_indices)
    for i, lab in enumerate(labels):
        if i in used:
            status = "used"
        elif i in duplicates:
            status = "excluded: duplicate of an earlier channel"
        elif lab.kind in ("electrode", "bipolar"):
            status = "recognized, not needed for the montage"
        else:
            status = EXCLUSION_REASONS[lab.kind]
        plan.channel_log.append({"raw_label": lab.raw, "kind": lab.kind,
                                 "canonical": lab.canonical, "status": status})
    return plan


# ---------------------------------------------------------------- units, resampling

def microvolt_factor(unit: str) -> float | None:
    u = unit.strip().replace("\u00b5", "u").replace("\u03bc", "u").lower()
    return {"uv": 1.0, "mv": 1e3, "v": 1e6, "nv": 1e-3}.get(u)


def resample(x: np.ndarray, fs_in: float, fs_out: float = TARGET_FS) -> np.ndarray:
    """Polyphase resampling with anti-aliasing (scipy.signal.resample_poly)."""
    if abs(fs_in - fs_out) < 1e-9:
        return x
    ratio = Fraction(fs_out / fs_in).limit_denominator(1000)
    if abs(fs_in * ratio.numerator / ratio.denominator - fs_out) > 1e-6:
        raise ValueError(f"cannot resample {fs_in} Hz to {fs_out} Hz with a rational ratio")
    return resample_poly(x, ratio.numerator, ratio.denominator, axis=-1)


def expected_length(n_in: int, fs_in: float, fs_out: float = TARGET_FS) -> int:
    """Number of samples resample() returns for n_in input samples."""
    if abs(fs_in - fs_out) < 1e-9:
        return n_in
    ratio = Fraction(fs_out / fs_in).limit_denominator(1000)
    return -(-n_in * ratio.numerator // ratio.denominator)  # ceiling division


# ---------------------------------------------------------------- harmonize

@dataclass
class HarmonizedRecording:
    data: np.ndarray            # (18, n_samples), microvolts, NaN rows for absent derivations
    present: np.ndarray         # (18,) bool
    fs: float
    sources: list[str]          # how each derivation was obtained
    channel_log: list[dict]
    warnings: list[str]
    derivations: tuple = DERIVATIONS
    t0: float = 0.0             # time of the first sample, seconds from recording start

    @property
    def n_samples(self) -> int:
        return self.data.shape[1]

    @property
    def duration_s(self) -> float:
        return self.n_samples / self.fs


def build_montage(plan: MontagePlan, signals: dict[int, np.ndarray], n: int) -> np.ndarray:
    """Combine channel signals (same rate and length) into the 18 derivations (float64)."""
    out = np.full((len(MONTAGE), n), np.nan)
    for k, step in enumerate(plan.steps):
        kind = step[0]
        if kind == "direct":
            out[k] = signals[step[1]][:n]
        elif kind == "reversed":
            out[k] = -signals[step[1]][:n]
        elif kind == "referential":
            out[k] = signals[step[1]][:n] - signals[step[2]][:n]
    return out


def harmonize(hdr: EDFHeader, target_fs: float = TARGET_FS, start_s: float = 0.0,
              stop_s: float | None = None, pad_s: float = 2.0) -> HarmonizedRecording:
    """Read one EDF and return it in the common format.

    With start_s and stop_s, only that stretch is returned (t0 = start_s). The
    read is padded by pad_s on each side and trimmed after resampling, so
    samples match a whole-recording harmonization (resampling filters are much
    shorter than the padding).
    """
    plan = plan_montage(hdr.labels)
    warnings = []
    idx = plan.used_indices
    whole = start_s <= 0 and (stop_s is None or stop_s >= hdr.duration_s)
    if whole:
        r0, r1, trim = 0, hdr.n_records, None
    else:
        stop_s = hdr.duration_s if stop_s is None else min(stop_s, hdr.duration_s)
        a, b = max(0.0, start_s - pad_s), min(hdr.duration_s, stop_s + pad_s)
        r0 = int(math.floor(a / hdr.record_s))
        r1 = min(hdr.n_records, int(math.ceil(b / hdr.record_s)))
        seg_t0 = r0 * hdr.record_s
        i0 = int(round((start_s - seg_t0) * target_fs))
        trim = (i0, i0 + int(round((stop_s - start_s) * target_fs)))
    raw = read_signals(hdr, idx, r0, r1 - r0) if idx else []
    signals = {}
    for i, x in zip(idx, raw):
        factor = microvolt_factor(hdr.units[i])
        if factor is None:
            warnings.append(f"{hdr.labels[i]}: unknown unit '{hdr.units[i]}', assumed microvolts")
            factor = 1.0
        signals[i] = resample(x * factor, hdr.fs(i), target_fs)
    if signals:
        n = min(len(s) for s in signals.values())
        if max(len(s) for s in signals.values()) - n > 1:
            warnings.append("channels had different lengths after resampling; trimmed to the shortest")
    else:
        n = int(round((r1 - r0) * hdr.record_s * target_fs))
        warnings.append("no derivation could be built from this recording")
    data = build_montage(plan, signals, n)
    t0 = 0.0
    if trim is not None:
        data = data[:, trim[0]:min(trim[1], n)]
        t0 = start_s
    return HarmonizedRecording(
        data=data,
        present=plan.present,
        fs=float(target_fs),
        sources=[plan.source(k) for k in range(len(MONTAGE))],
        channel_log=plan.channel_log,
        warnings=warnings,
        t0=t0,
    )

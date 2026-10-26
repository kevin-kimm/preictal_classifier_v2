"""D2 improvement round (docs/evaluation_methods.md v1.25, Section 14).

Helpers shared by scripts/run_d2_plus.py, scripts/d2_plus_alarms.py and the purity count:

* alternative labels for windows that were already extracted: a different preictal length (training
  labels only, or train and test), or labels taken at each window's *start* instead of its end, to find
  windows that straddle two states;
* alarm-level and time-level PPV/NPV from saved window scores.

Nothing here changes the frozen pipeline: features, the frozen label rules and the stored labels are
read as they are, and every alternative label is computed next to them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from ..alarm.alarm import alarm_times
from ..data.labels import EXCLUDED, ICTAL, INTERICTAL, PREICTAL, LabelRules, labels_at


# ------------------------------------------------------------------ alternative labels

def _with_own_file(lab: np.ndarray, times: np.ndarray, p, tl, rules: LabelRules) -> np.ndarray:
    """SeizeIT2 rule (evaluation methods v1.13): preictal only inside the seizure's own file."""
    same = np.zeros(len(times), dtype=bool)
    for ev in tl.events:
        if ev.eligible and p.start <= ev.onset < p.end:
            same |= (times >= ev.onset - rules.preictal_start_s) & (times <= ev.onset - rules.sph_s)
    lab = lab.copy()
    lab[(lab == PREICTAL) & ~same] = EXCLUDED
    return lab


def label_lookup(timelines, rules: LabelRules, length_s: float, step_s: float, at: str = "end",
                 own_file: bool = False) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """rel_path -> (window starts, labels) under `rules`, labeling each window at its end (as the
    frozen pipeline does) or at its start (to find windows that contain two states)."""
    if at not in ("end", "start"):
        raise ValueError("at must be 'end' or 'start'")
    out = {}
    for tl in timelines:
        for p in tl.placed:
            if p.duration < length_s:
                out[p.rec.rel_path] = (np.array([]), np.array([], dtype=np.int8))
                continue
            starts = np.arange(0.0, p.duration - length_s + 1e-9, step_s)
            times = p.start + starts + (length_s if at == "end" else 0.0)
            lab = labels_at(times, tl, rules)
            if own_file:
                lab = _with_own_file(lab, times, p, tl, rules)
            out[p.rec.rel_path] = (starts, lab.astype(np.int8))
    return out


def map_labels(W, lookup: dict[str, tuple[np.ndarray, np.ndarray]]) -> np.ndarray:
    """Labels from a lookup for every loaded window (rows of W), matched by recording and start time."""
    out = np.full(len(W.y), EXCLUDED, dtype=np.int8)
    for code, name in enumerate(W.recordings):
        idx = np.flatnonzero(W.recording == code)
        if name not in lookup:
            raise KeyError(f"no labels for {name}; were the timelines built from the same raw data?")
        st, lab = lookup[name]
        pos = np.searchsorted(st, W.starts[idx])
        if len(st) == 0 or np.any(pos >= len(st)) or not np.allclose(st[np.minimum(pos, len(st) - 1)], W.starts[idx]):
            raise ValueError(f"window starts of {name} don't match the timeline; re-run the feature extraction")
        out[idx] = lab[pos]
    return out


def build_timelines_for(dataset: str, repo: Path, rules: LabelRules, subjects=None):
    """Timelines for CHB-MIT and Siena (frozen loader) or SeizeIT2 (frozen adapter), under `rules`."""
    if dataset == "seizeit2":
        from ..data.seizeit2 import discover_patient, timeline
        root = repo / "data" / "raw" / "seizeit2_v1.1.0"
        subs = sorted(s.split(":", 1)[1] for s in subjects)
        return [timeline(discover_patient(root, s), rules) for s in subs]
    from ..data.labels import build_timelines
    from ..data.loaders import discover
    return build_timelines(discover(repo / "data" / "raw", datasets=("chbmit", "siena")), rules)


def alternative_labels(W, dataset: str, repo: Path, rules: LabelRules, length_s: float, step_s: float,
                       at: str = "end", subjects=None, check_frozen: bool = False) -> np.ndarray:
    """Labels for the loaded windows under `rules`. With check_frozen (frozen rules, at='end') the result
    must equal the stored labels, which checks the mapping itself."""
    tls = build_timelines_for(dataset, repo, rules, subjects)
    lab = map_labels(W, label_lookup(tls, rules, length_s, step_s, at, own_file=dataset == "seizeit2"))
    if check_frozen and not np.array_equal(lab, W.y):
        raise ValueError("recomputed frozen labels differ from the stored ones")
    return lab


def preictal_rules(rules: LabelRules, minutes: float) -> LabelRules:
    """The frozen rules with a different preictal length (the 5 s horizon, 4 h gap and 90% rule kept)."""
    return replace(rules, preictal_start_s=float(minutes) * 60.0)


def impure(end_labels: np.ndarray, start_labels: np.ndarray) -> np.ndarray:
    """Windows whose first and last moments fall in different states."""
    return np.asarray(end_labels) != np.asarray(start_labels)


# ------------------------------------------------------------------ PPV / NPV from window scores

@dataclass
class TimeConfusion:
    """Every scored window counted once, by whether a warning was on and whether a seizure followed.

    A window is "warning" if an alarm went off in the 30 min before it (the refractory period, the time
    the user is warned for). It is "seizure ahead" if a seizure onset follows within sph_s to horizon_s
    of its end. PPV = P(seizure ahead | warning on); NPV = P(no seizure ahead | warning off).
    """
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    def add(self, o: "TimeConfusion") -> "TimeConfusion":
        return TimeConfusion(self.tp + o.tp, self.fp + o.fp, self.fn + o.fn, self.tn + o.tn)

    @property
    def ppv(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else float("nan")

    @property
    def npv(self) -> float:
        return self.tn / (self.tn + self.fn) if self.tn + self.fn else float("nan")

    @property
    def sensitivity(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else float("nan")

    @property
    def specificity(self) -> float:
        return self.tn / (self.tn + self.fp) if self.tn + self.fp else float("nan")


def time_confusion(times: np.ndarray, scores: np.ndarray, onsets: np.ndarray, threshold, sph_s: float = 5.0,
                   horizon_s: float = 1800.0, refractory_s: float = 1800.0, smoothing: int = 1,
                   persistence: int = 1, keep: np.ndarray | None = None) -> TimeConfusion:
    """TimeConfusion for one continuous sequence of windows. `keep` selects which windows are counted
    (e.g. not the smoothing warm-up)."""
    times = np.asarray(times, float)
    alarms = alarm_times(times, scores, threshold, refractory_s, smoothing, persistence)
    warn = np.zeros(len(times), dtype=bool)
    for a in alarms:
        warn |= (times >= a) & (times < a + refractory_s)
    ahead = np.zeros(len(times), dtype=bool)
    for on in np.asarray(onsets, float):
        d = on - times
        ahead |= (d >= sph_s) & (d <= horizon_s)
    k = np.ones(len(times), bool) if keep is None else np.asarray(keep, bool)
    w, a = warn[k], ahead[k]
    return TimeConfusion(int((w & a).sum()), int((w & ~a).sum()), int((~w & a).sum()), int((~w & ~a).sum()))


def window_confusion(labels: np.ndarray, scores: np.ndarray, threshold: float) -> dict:
    """Preictal vs interictal windows at one score threshold (no smoothing or refractory period)."""
    pi = np.isin(labels, (PREICTAL, INTERICTAL))
    y, s = labels[pi] == PREICTAL, np.asarray(scores)[pi] >= threshold
    tp, fp = int((y & s).sum()), int((~y & s).sum())
    fn, tn = int((y & ~s).sum()), int((~y & ~s).sum())
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "ppv": tp / (tp + fp) if tp + fp else float("nan"),
            "npv": tn / (tn + fn) if tn + fn else float("nan"),
            "sensitivity": tp / (tp + fn) if tp + fn else float("nan"),
            "specificity": tn / (tn + fp) if tn + fp else float("nan"),
            "prevalence": (tp + fn) / max(tp + fp + fn + tn, 1)}


TRAINABLE = (PREICTAL, ICTAL, INTERICTAL)
HORIZON_H = 0.5          # a warning covers the next 30 min


def alarm_ppv_npv(seizures: int, warned: int, false_alarms: int, interictal_h: float,
                  true_alarms: int | None = None, horizon_h: float = HORIZON_H) -> dict:
    """Alarm-level PPV and NPV from counts.

    PPV  = true alarms / all alarms. If true alarms weren't counted, warned seizures stand in for them
           (with a 30 min refractory period a seizure rarely gets two true alarms, so this is at most
           slightly low).
    NPV  = share of warning-free stretches (one horizon long) not followed by a seizure. Time is the
           interictal hours plus one horizon per seizure, and each alarm covers one horizon.
    """
    ta = warned if true_alarms is None else true_alarms
    alarms = ta + false_alarms
    total_h = interictal_h + horizon_h * seizures
    free_blocks = max(total_h - horizon_h * alarms, 0.0) / horizon_h
    missed = seizures - warned
    return {"sensitivity": warned / seizures if seizures else float("nan"),
            "far_per_24h": 24 * false_alarms / interictal_h if interictal_h else float("nan"),
            "ppv": ta / alarms if alarms else float("nan"),
            "npv": 1 - missed / free_blocks if free_blocks else float("nan"),
            "seizures_per_day_in_data": 24 * seizures / total_h if total_h else float("nan")}


def home_ppv_npv(sens: float, far_per_24h: float, rate_per_day: float,
                 horizon_h: float = HORIZON_H) -> tuple[float, float]:
    """PPV and NPV if the same sensitivity and false-alarm rate held at a home seizure rate (per day)."""
    true_per_day = sens * rate_per_day
    ppv = true_per_day / (true_per_day + far_per_24h) if (true_per_day + far_per_24h) else float("nan")
    blocks_free = max(24 / horizon_h - (true_per_day + far_per_24h), 1e-9)
    npv = 1 - (1 - sens) * rate_per_day / blocks_free
    return ppv, npv

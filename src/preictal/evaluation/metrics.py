"""Evaluation metrics (REQ-E4), as defined in docs/verification_plan.md, Section 3.

Window level: AUROC (preictal vs interictal), three-class confusion matrix and
macro F1. Event level: sensitivity, false alarms per 24 h, time in warning,
warning time, and comparison with a random predictor (Schelter et al., 2006).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import binomtest
from sklearn.metrics import confusion_matrix, f1_score, roc_auc_score

from ..alarm.alarm import alarm_times
from ..data.labels import EXCLUDED, ICTAL, INTERICTAL, PREICTAL


@dataclass
class Sequence:
    """The windows of one timeline, in time order, with that timeline's seizures."""
    subject: str
    times: np.ndarray            # window end times, seconds on the timeline
    scores: np.ndarray
    labels: np.ndarray
    onsets: np.ndarray           # every annotated seizure onset on the timeline
    eligible_onsets: np.ndarray  # onsets of eligible events (targets for sensitivity)


@dataclass
class AlarmResult:
    n_events: int = 0
    n_predicted: int = 0
    n_alarms: int = 0
    n_false: int = 0
    far_hours: float = 0.0       # hours outside preictal and ictal
    n_windows: int = 0
    n_warning_windows: int = 0
    warning_times: list = field(default_factory=list)

    @property
    def sensitivity(self) -> float:
        return self.n_predicted / self.n_events if self.n_events else float("nan")

    @property
    def far_per_24h(self) -> float:
        return 24 * self.n_false / self.far_hours if self.far_hours > 0 else float("nan")

    @property
    def time_in_warning(self) -> float:
        return self.n_warning_windows / self.n_windows if self.n_windows else float("nan")

    def add(self, other: "AlarmResult") -> "AlarmResult":
        return AlarmResult(self.n_events + other.n_events, self.n_predicted + other.n_predicted,
                           self.n_alarms + other.n_alarms, self.n_false + other.n_false,
                           self.far_hours + other.far_hours, self.n_windows + other.n_windows,
                           self.n_warning_windows + other.n_warning_windows,
                           self.warning_times + other.warning_times)


def evaluate_alarms(seq: Sequence, threshold: float, step_s: float, sph_s: float = 5.0,
                    horizon_s: float = 1800.0, refractory_s: float = 1800.0,
                    smoothing: int = 1, persistence: int = 1) -> AlarmResult:
    """Alarm metrics for one timeline.

    An alarm at time a is true if a seizure onset follows between sph_s and
    horizon_s later (5 s to 30 min); otherwise it is false. An eligible event is
    predicted if at least one alarm falls in that range before its onset.
    """
    alarms = alarm_times(seq.times, seq.scores, threshold, refractory_s, smoothing, persistence)
    lead = seq.onsets[None, :] - alarms[:, None] if len(alarms) and len(seq.onsets) else np.empty((len(alarms), 0))
    true = ((lead >= sph_s) & (lead <= horizon_s)).any(axis=1) if lead.size else np.zeros(len(alarms), bool)
    predicted = 0
    for on in seq.eligible_onsets:
        d = on - alarms
        predicted += bool(((d >= sph_s) & (d <= horizon_s)).any())
    warn = []
    for a, is_true in zip(alarms, true):
        if is_true:
            d = seq.onsets - a
            warn.append(float(d[(d >= sph_s) & (d <= horizon_s)].min()))
    in_warning = np.zeros(len(seq.times), dtype=bool)
    for a in alarms:
        in_warning |= (seq.times >= a) & (seq.times < a + refractory_s)
    far_windows = np.isin(seq.labels, (INTERICTAL, EXCLUDED)).sum()
    return AlarmResult(len(seq.eligible_onsets), predicted, len(alarms), int((~true).sum()),
                       far_windows * step_s / 3600, len(seq.times), int(in_warning.sum()), warn)


def evaluate_all(seqs: list[Sequence], threshold: float, step_s: float, **kw) -> AlarmResult:
    total = AlarmResult()
    for s in seqs:
        total = total.add(evaluate_alarms(s, threshold, step_s, **kw))
    return total


def false_alarm_rate(seqs: list[Sequence], threshold: float, step_s: float, sph_s: float = 5.0,
                     horizon_s: float = 1800.0, refractory_s: float = 1800.0, smoothing: int = 1,
                     persistence: int = 1) -> float:
    """False alarms per 24 h over the given timelines (fast path used for the threshold search)."""
    n_false, hours = 0, 0.0
    for s in seqs:
        alarms = alarm_times(s.times, s.scores, threshold, refractory_s, smoothing, persistence)
        if len(alarms) and len(s.onsets):
            lead = s.onsets[None, :] - alarms[:, None]
            n_false += int((~((lead >= sph_s) & (lead <= horizon_s)).any(axis=1)).sum())
        else:
            n_false += len(alarms)
        hours += np.isin(s.labels, (INTERICTAL, EXCLUDED)).sum() * step_s / 3600
    return 24 * n_false / hours if hours > 0 else float("nan")


def choose_threshold(seqs: list[Sequence], far_target_per_24h: float, step_s: float,
                     n_candidates: int = 1000, **kw) -> tuple[float, float]:
    """Lowest of n_candidates evenly spaced thresholds in [0, 1] whose FAR is at most the target.

    Returns (threshold, FAR at that threshold). If no candidate meets the target,
    returns (1.0, FAR at 1.0).
    """
    for thr in np.linspace(0.0, 1.0, n_candidates):
        far = false_alarm_rate(seqs, thr, step_s, **kw)
        if not math.isnan(far) and far <= far_target_per_24h:
            return float(thr), float(far)
    return 1.0, float(false_alarm_rate(seqs, 1.0, step_s, **kw))


def choose_threshold_bisect(seqs: list[Sequence], far_target_per_24h: float, step_s: float,
                            n_candidates: int = 1000, **kw) -> tuple[float, float]:
    """Same candidates and rule as choose_threshold, found by binary search.

    Assumes the false alarm rate doesn't rise as the threshold rises, which holds
    closely but not exactly with a refractory period. Used in D2, where the search
    runs many more times (docs/evaluation_methods.md v1.2).
    """
    grid = np.linspace(0.0, 1.0, n_candidates)
    lo, hi = 0, n_candidates - 1
    if not false_alarm_rate(seqs, grid[hi], step_s, **kw) <= far_target_per_24h:
        return 1.0, float(false_alarm_rate(seqs, 1.0, step_s, **kw))
    while lo < hi:
        mid = (lo + hi) // 2
        if false_alarm_rate(seqs, grid[mid], step_s, **kw) <= far_target_per_24h:
            hi = mid
        else:
            lo = mid + 1
    return float(grid[lo]), float(false_alarm_rate(seqs, grid[lo], step_s, **kw))


def chance_p_value(n_predicted: int, n_events: int, far_per_24h: float, sop_s: float = 1795.0) -> tuple[float, float]:
    """Probability that a random predictor with the same FAR predicts a seizure, and the one-sided p-value."""
    if n_events == 0 or math.isnan(far_per_24h):
        return float("nan"), float("nan")
    p_chance = 1 - math.exp(-(far_per_24h / 24.0) * (sop_s / 3600.0))
    p_chance = min(max(p_chance, 1e-12), 1 - 1e-12)
    return p_chance, float(binomtest(n_predicted, n_events, p_chance, alternative="greater").pvalue)


def window_metrics(labels: np.ndarray, proba: np.ndarray) -> dict:
    """AUROC (preictal vs interictal), confusion matrix and macro F1 over labeled windows.

    proba columns are ordered preictal, ictal, interictal.
    """
    out = {"auroc": float("nan")}
    pi = np.isin(labels, (PREICTAL, INTERICTAL))
    y = labels[pi] == PREICTAL
    if y.any() and (~y).any():
        out["auroc"] = float(roc_auc_score(y, proba[pi, 0]))
    lab = np.isin(labels, (PREICTAL, ICTAL, INTERICTAL))
    order = np.array([PREICTAL, ICTAL, INTERICTAL])
    pred = order[np.argmax(proba[lab], axis=1)]
    out["confusion"] = confusion_matrix(labels[lab], pred, labels=order).tolist()
    out["macro_f1"] = float(f1_score(labels[lab], pred, labels=order, average="macro", zero_division=0))
    return out


def bootstrap_ci(values, n: int = 1000, seed: int = 0, level: float = 0.95) -> tuple[float, float]:
    """Percentile bootstrap interval for the mean, resampling the given values (patients)."""
    v = np.asarray([x for x in values if not math.isnan(x)], dtype=float)
    if len(v) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = rng.choice(v, size=(n, len(v)), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(lo), float(hi)

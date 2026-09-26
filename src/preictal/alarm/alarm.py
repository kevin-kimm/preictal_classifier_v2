"""Alarm logic (REQ-A1, REQ-A2).

Turns a sequence of risk scores into discrete alarms:

1. smoothing: each score is replaced by the mean of the last `smoothing` scores
   (1 = no smoothing);
2. persistence: the smoothed score must have been at or above the threshold for
   the last `persistence` windows in a row;
3. refractory period: after an alarm, no new alarm for `refractory_s` seconds.

Every step only looks at the current and earlier windows, so an alarm at time t
never depends on scores after t. D1 uses smoothing 1 and persistence 1
(docs/evaluation_methods.md, Section 7).
"""

from __future__ import annotations

import numpy as np


def smooth(scores: np.ndarray, n: int) -> np.ndarray:
    """Causal moving average over the last n values (fewer at the start)."""
    scores = np.asarray(scores, dtype=float)
    if n <= 1:
        return scores
    c = np.concatenate([[0.0], np.cumsum(scores)])
    idx = np.arange(1, len(scores) + 1)
    lo = np.maximum(idx - n, 0)
    return (c[idx] - c[lo]) / (idx - lo)


def candidates(scores: np.ndarray, threshold: float, smoothing: int = 1, persistence: int = 1) -> np.ndarray:
    """Boolean mask: windows where the alarm condition holds (before the refractory rule)."""
    above = smooth(scores, smoothing) >= threshold
    if persistence <= 1:
        return above
    idx = np.arange(len(above))
    last_below = np.maximum.accumulate(np.where(above, -1, idx))   # most recent window below threshold
    return idx - last_below >= persistence                          # length of the current run above it


def alarm_times(times: np.ndarray, scores: np.ndarray, threshold: float, refractory_s: float = 1800.0,
                smoothing: int = 1, persistence: int = 1) -> np.ndarray:
    """Times of alarms for one continuous sequence of windows (times in increasing order).

    Smoothing and persistence are applied along the sequence as given, so pass
    one timeline at a time.
    """
    times = np.asarray(times, dtype=float)
    cand = times[candidates(scores, threshold, smoothing, persistence)]
    alarms, pos = [], 0
    while pos < len(cand):
        alarms.append(cand[pos])
        pos = int(np.searchsorted(cand, cand[pos] + refractory_s, side="left"))
    return np.array(alarms)

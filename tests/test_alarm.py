"""VT-16: alarm logic tests. See docs/verification_plan.md.

(VT-16 is formally a Deliverable 2 test; these checks already cover the D1
alarm logic, which uses smoothing 1 and persistence 1.)
"""

import numpy as np

from preictal.alarm.alarm import alarm_times, smooth

STEP = 5.0


def trace(minutes, value=0.0):
    n = int(minutes * 60 / STEP)
    return np.arange(1, n + 1) * STEP, np.full(n, value)


def test_sustained_high_score_gives_alarms_30_min_apart():
    t, s = trace(120, 0.9)                       # (a) above threshold for 2 h
    a = alarm_times(t, s, threshold=0.5)
    assert len(a) == 4 and np.all(np.diff(a) >= 1800)


def test_short_spike_is_ignored_with_persistence():
    t, s = trace(30)
    s[100:102] = 0.9                             # (b) 2 windows = 10 s
    assert len(alarm_times(t, s, 0.5, persistence=3)) == 0
    assert len(alarm_times(t, s, 0.5, persistence=1)) == 1


def test_oscillating_score_does_not_repeat_inside_refractory():
    t, _ = trace(60)
    s = np.where(np.arange(len(t)) % 2 == 0, 0.6, 0.4)   # (c) bouncing around the threshold
    a = alarm_times(t, s, 0.5)
    assert len(a) == 2 and a[1] - a[0] >= 1800


def test_alarms_are_causal():
    t, s = trace(90)
    s[200] = 0.9
    before = alarm_times(t, s, 0.5)
    changed = s.copy()
    changed[400:] = 0.95                         # (d) change everything after t[400]
    after = alarm_times(t, changed, 0.5)
    assert np.array_equal(after[after < t[400]], before[before < t[400]])


def test_smoothing_is_a_trailing_mean():
    x = np.array([0, 0, 3, 3, 3], dtype=float)
    assert np.allclose(smooth(x, 3), [0, 0, 1, 2, 3])
    assert np.array_equal(smooth(x, 1), x)

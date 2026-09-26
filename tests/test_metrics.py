"""Metric definitions (docs/verification_plan.md, Section 3)."""

import math

import numpy as np
import pytest

from preictal.data.labels import EXCLUDED, ICTAL, INTERICTAL, PREICTAL
from preictal.evaluation.metrics import (
    Sequence, bootstrap_ci, chance_p_value, choose_threshold, evaluate_alarms, window_metrics,
)

STEP = 5.0


def seq(hours, onsets=(), eligible=True, labels=None):
    t = np.arange(1, int(hours * 3600 / STEP) + 1) * STEP
    lab = np.full(len(t), INTERICTAL, dtype=np.int8) if labels is None else labels
    onsets = np.array(onsets, dtype=float)
    return Sequence("s", t, np.zeros(len(t)), lab, onsets, onsets if eligible else np.array([]))


@pytest.mark.parametrize("lead, true", [(4.9, False), (5, True), (600, True), (1800, True), (1800.1, False)])
def test_true_alarm_window_is_5_s_to_30_min(lead, true):
    onset = 7200.0
    s = Sequence("s", np.array([onset - lead]), np.array([1.0]), np.array([EXCLUDED], dtype=np.int8),
                 np.array([onset]), np.array([onset]))
    r = evaluate_alarms(s, 0.5, STEP)
    assert r.n_predicted == int(true) and r.n_false == int(not true)
    if true:
        assert r.warning_times == [pytest.approx(lead)]


def test_false_alarm_rate_per_24h():
    s = seq(12)
    s.scores[[100, 1000, 2000]] = 1.0            # 3 alarms, more than 30 min apart, no seizures
    r = evaluate_alarms(s, 0.5, STEP)
    assert r.n_false == 3 and r.far_hours == pytest.approx(12)
    assert r.far_per_24h == pytest.approx(6.0)


def test_far_hours_leave_out_preictal_and_ictal():
    lab = np.array([PREICTAL] * 720 + [ICTAL] * 12 + [EXCLUDED] * 708 + [INTERICTAL] * 720, dtype=np.int8)
    s = seq(3, labels=lab)
    assert evaluate_alarms(s, 0.5, STEP).far_hours == pytest.approx((708 + 720) * STEP / 3600)


def test_time_in_warning():
    s = seq(2)
    s.scores[0] = 1.0                            # one alarm at 5 s -> 30 min of warning out of 2 h
    assert evaluate_alarms(s, 0.5, STEP).time_in_warning == pytest.approx(0.25, abs=0.01)


def test_threshold_is_lowest_meeting_target():
    s = seq(24)
    s.scores = np.linspace(0, 1, len(s.times))   # rising score: higher threshold -> fewer alarms
    thr, far = choose_threshold([s], 10, STEP, n_candidates=101)
    assert far <= 10
    lower = thr - 0.01
    from preictal.evaluation.metrics import false_alarm_rate
    assert false_alarm_rate([s], lower, STEP) > 10


def test_chance_level():
    p, pval = chance_p_value(8, 10, far_per_24h=2.4, sop_s=1795)
    assert p == pytest.approx(1 - math.exp(-0.1 * 1795 / 3600))
    assert pval < 0.001
    assert chance_p_value(0, 10, 2.4)[1] == pytest.approx(1.0)


def test_window_metrics():
    labels = np.array([PREICTAL, PREICTAL, INTERICTAL, INTERICTAL, ICTAL, EXCLUDED])
    proba = np.array([[.9, .05, .05], [.6, .1, .3], [.2, .1, .7], [.4, .1, .5], [.1, .8, .1], [1, 0, 0]])
    m = window_metrics(labels, proba)
    assert m["auroc"] == 1.0 and m["macro_f1"] == 1.0
    assert np.array(m["confusion"]).sum() == 5    # excluded window not counted


def test_bootstrap_ci_contains_mean():
    lo, hi = bootstrap_ci([0.5, 0.6, 0.7, 0.8], n=500)
    assert lo <= 0.65 <= hi


def test_bisect_matches_linear_scan_when_far_is_monotone():
    from preictal.evaluation.metrics import choose_threshold_bisect
    s = seq(24)
    s.scores = np.linspace(0, 1, len(s.times))
    assert choose_threshold_bisect([s], 10, STEP, 101) == choose_threshold([s], 10, STEP, 101)


def test_persistence_run_length():
    from preictal.alarm.alarm import candidates
    x = np.array([0, 1, 1, 0, 1, 1, 1, 1], dtype=float)
    assert candidates(x, 0.5, persistence=3).tolist() == [False] * 6 + [True, True]

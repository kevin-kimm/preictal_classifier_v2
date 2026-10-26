"""Tests for the D2 improvement round (docs/evaluation_methods.md v1.25, Section 14)."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from preictal.data.labels import (
    EXCLUDED, ICTAL, INTERICTAL, PREICTAL, LabelRules, build_timelines, window_labels,
)
from preictal.data.loaders import Recording
from preictal.evaluation.d2_plus import (
    alarm_ppv_npv, home_ppv_npv, impure, label_lookup, map_labels, preictal_rules, time_confusion,
    window_confusion,
)
from preictal.features.slow import DECIM_FS, LOOKBACK_S, decimate_causal, pool_slow, slow_features

R = LabelRules()
H = 3600.0


def one_patient():
    r = Recording("siena", Path("PN00-1.edf"), "PN00-1.edf", "PN00", "siena:PN00",
                  seizures=[(5 * H, 5 * H + 60), (9.5 * H, 9.5 * H + 40)])
    (tl,) = build_timelines([r], R, {"PN00-1.edf": (0, 14 * H)})
    return tl


def test_lookup_at_end_matches_frozen_window_labels():
    tl = one_patient()
    lk = label_lookup([tl], R, 30.0, 5.0)
    starts, lab = window_labels(tl.placed[0], tl, R, 30.0, 5.0)
    assert np.array_equal(lk["PN00-1.edf"][0], starts)
    assert np.array_equal(lk["PN00-1.edf"][1], lab)


def test_windows_straddling_two_states_are_only_at_boundaries():
    tl = one_patient()
    end = label_lookup([tl], R, 30.0, 5.0, at="end")["PN00-1.edf"][1]
    start = label_lookup([tl], R, 30.0, 5.0, at="start")["PN00-1.edf"][1]
    mixed = impure(end, start)
    # each state boundary affects at most 30 s / 5 s = 6 windows
    changes = np.count_nonzero(np.diff(end.astype(int)))
    assert 0 < mixed.sum() <= 6 * changes
    # preictal windows that straddle a boundary are the first ones of each preictal period
    pre = np.flatnonzero((end == PREICTAL) & mixed)
    assert all(start[i] == EXCLUDED for i in pre)


def test_preictal_length_moves_only_preictal_and_excluded():
    tl = one_patient()
    base = label_lookup([tl], R, 30.0, 5.0)["PN00-1.edf"][1]
    for minutes in (10, 20, 45, 60):
        alt = label_lookup([tl], preictal_rules(R, minutes), 30.0, 5.0)["PN00-1.edf"][1]
        assert np.array_equal(alt == INTERICTAL, base == INTERICTAL)
        assert np.array_equal(alt == ICTAL, base == ICTAL)
        changed = alt != base
        assert set(np.unique(alt[changed])) <= {PREICTAL, EXCLUDED}
        n_pre = (alt == PREICTAL).sum()
        assert n_pre == pytest.approx(2 * (minutes * 60 - 5) / 5 + 2, abs=2)


def test_map_labels_matches_rows_and_refuses_mismatches():
    lookup = {"a.edf": (np.array([0.0, 5.0, 10.0, 15.0]), np.array([2, 2, 0, 0], np.int8)),
              "b.edf": (np.array([0.0, 5.0]), np.array([3, 1], np.int8))}
    W = SimpleNamespace(y=np.zeros(5, np.int8), recordings=["b.edf", "a.edf"],
                        recording=np.array([1, 1, 0, 1, 0]), starts=np.array([15.0, 0.0, 5.0, 10.0, 0.0]))
    assert map_labels(W, lookup).tolist() == [0, 2, 1, 0, 3]
    W.starts = np.array([15.0, 0.0, 7.0, 10.0, 0.0])
    with pytest.raises(ValueError):
        map_labels(W, lookup)


def test_time_confusion_counts_warning_time():
    t = np.arange(0, 7200, 5.0)
    s = np.zeros(len(t))
    onset = 6000.0
    s[(t >= onset - 900) & (t < onset - 880)] = 1.0          # one alarm 15 min before onset
    tc = time_confusion(t, s, [onset], 0.5, refractory_s=1800.0)
    ahead = (onset - t >= 5) & (onset - t <= 1800)
    warn = (t >= onset - 900) & (t < onset - 900 + 1800)
    assert tc.tp == int((ahead & warn).sum())
    assert tc.fn == int((ahead & ~warn).sum())
    assert tc.fp == int((~ahead & warn).sum())
    assert tc.tn == int((~ahead & ~warn).sum())
    assert 0 < tc.ppv < 1 and 0 < tc.npv <= 1


def test_window_confusion():
    lab = np.array([PREICTAL, PREICTAL, INTERICTAL, INTERICTAL, INTERICTAL, ICTAL])
    s = np.array([0.9, 0.2, 0.8, 0.1, 0.1, 0.99])
    c = window_confusion(lab, s, 0.5)
    assert (c["tp"], c["fn"], c["fp"], c["tn"]) == (1, 1, 1, 2)
    assert c["ppv"] == pytest.approx(0.5) and c["npv"] == pytest.approx(2 / 3)


def test_ppv_npv_from_counts():
    m = alarm_ppv_npv(seizures=10, warned=4, false_alarms=6, interictal_h=48.0)
    assert m["ppv"] == pytest.approx(0.4)
    assert m["far_per_24h"] == pytest.approx(3.0)
    assert 0.9 < m["npv"] < 1
    never = alarm_ppv_npv(seizures=10, warned=0, false_alarms=0, interictal_h=48.0)
    assert np.isnan(never["ppv"]) and never["npv"] > 0.9       # NPV is high even for a device that never alarms
    ppv_day, npv_day = home_ppv_npv(0.4, 5.0, 1.0)
    ppv_month, _ = home_ppv_npv(0.4, 5.0, 1 / 30)
    assert ppv_day == pytest.approx(0.4 / 5.4) and ppv_month < ppv_day and npv_day > 0.98


def test_slow_features_see_infraslow_power_and_are_causal():
    fs = 256.0
    n = int(900 * fs)
    t = np.arange(n) / fs
    rng = np.random.default_rng(0)
    quiet = rng.normal(0, 5, n)
    slow = quiet + 200 * np.sin(2 * np.pi * 0.05 * t)
    x = np.vstack([quiet, slow, np.full(n, np.nan)])
    ends = np.array([200.0, 400.0, 600.0])
    f = slow_features(x, fs, 0.0, ends)
    assert np.isnan(f[0]).all()                              # not 5 min of history yet
    assert f[1, 1, 0] > f[1, 0, 0] + 2                       # 0.01-0.1 Hz power much higher with the 0.05 Hz wave
    assert np.isnan(f[1, 2]).all()                           # absent channel
    later = x.copy()
    later[:, int(400 * fs) + 1:] += 1000.0                   # change everything after the second window's end
    f2 = slow_features(later, fs, 0.0, ends)
    assert np.allclose(f[1], f2[1], equal_nan=True)           # causal: the second window is unchanged
    pooled = pool_slow(f)
    assert pooled.shape == (3, 12)
    assert LOOKBACK_S == 300.0 and decimate_causal(x[:2], fs).shape[1] == n // int(fs / DECIM_FS)

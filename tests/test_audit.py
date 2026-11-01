"""Annotation and artifact audit helpers (evaluation methods v1.32, Section 14.16)."""

import numpy as np

from preictal.evaluation.audit import artifact_flags, onset_check, recent, runs


def test_runs_split_on_gaps_and_timelines():
    t = np.array([0, 5, 10, 15, 100, 105, 110, 0, 5, 10.0])
    tl = np.array([0, 0, 0, 0, 0, 0, 0, 1, 1, 1])
    m = np.array([1, 1, 1, 0, 1, 1, 1, 1, 1, 1], bool)
    # 100 follows 15 after a gap; timeline 1 starts a new run
    assert runs(m, t, tl, 5.0) == [(0, 2), (4, 6), (7, 9)]
    assert runs(m, t, tl, 5.0, min_len=4) == []
    m2 = np.array([0, 1, 1, 1, 1, 1, 1, 0, 0, 0], bool)
    assert runs(m2, t, tl, 5.0, min_len=3) == [(1, 3), (4, 6)]


def test_artifact_flags_are_relative_to_each_channel():
    rms = np.array([[10, 50], [12, 55], [70, 50], [10, 2], [10, np.nan]], float)
    ref = np.array([1, 1, 0, 0, 0], bool)            # medians 11 and 52.5
    high, flat = artifact_flags(rms, ref)
    assert high.tolist() == [False, False, True, False, False]
    assert flat.tolist() == [False, False, False, True, False]   # an absent channel is never "flat"


def test_recent_looks_backwards_only():
    t = np.arange(0, 600, 5.0)
    tl = np.zeros(len(t), int)
    flag = t == 300
    r = recent(flag, t, tl, 180.0)
    assert not r[t < 300].any()
    assert r[(t >= 300) & (t < 480)].all()
    assert not r[t >= 480].any()


def test_onset_check_lead_and_detection():
    t = np.arange(-600, 300, 5.0)
    p = np.zeros(len(t))
    p[(t >= -40) & (t <= 60)] = 0.9                  # seizure-like from 40 s before the annotated onset
    r = onset_check(t, p, 0.5, 0.0, 5.0)
    assert r["detected"] and r["lead_s"] == 40.0 and not r["clipped"]
    p2 = np.zeros(len(t))
    p2[(t >= -100) & (t <= -50)] = 0.9               # a run that ends before onset doesn't count
    assert not onset_check(t, p2, 0.5, 0.0, 5.0)["detected"]
    p3 = np.zeros(len(t))
    p3[(t >= 10) & (t <= 20)] = 0.9                  # detected after onset: negative lead
    r3 = onset_check(t, p3, 0.5, 0.0, 5.0)
    assert r3["detected"] and r3["lead_s"] == -10.0

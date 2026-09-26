"""VT-06: labeling rule tests. See docs/verification_plan.md, Section 3 and D-5.

Recordings here are synthetic: only names, seizure times, start times of day
and durations matter, so no EDF files are needed.
"""

from pathlib import Path

import numpy as np
import pytest

from preictal.data.labels import (
    EXCLUDED, ICTAL, INTERICTAL, PREICTAL, LabelRules, build_timelines, label_intervals,
    labels_at, window_labels,
)
from preictal.data.loaders import Recording

R = LabelRules()          # 30 min preictal, 5 s gap, 4 h interictal, 30 min merge, 90% coverage
H = 3600.0


def rec(name, seizures=(), dataset="siena", patient="PN00", excluded=()):
    subject = f"tuh:{patient}" if dataset in ("tusz", "tuar") else f"{dataset}:{patient}"
    return Recording(dataset, Path(name), name, patient, subject, seizures=list(seizures),
                     excluded=[(a, b, "test") for a, b in excluded])


def timelines(recs, info):
    return build_timelines(recs, R, info)


def lab(tl, t):
    return int(labels_at(np.array([t]), tl, R)[0])


def test_rules_match_config():
    assert LabelRules.from_config() == R


# ---------------------------------------------------------------- one seizure, every boundary

@pytest.fixture
def single():
    r = rec("PN00-1.edf", seizures=[(5 * H, 5 * H + 60)])
    (tl,) = timelines([r], {"PN00-1.edf": (0, 10 * H)})
    return tl


@pytest.mark.parametrize("dt, expected", [
    (-4 * H, INTERICTAL),            # exactly 4 h before onset
    (-4 * H + 0.01, EXCLUDED),       # just inside 4 h
    (-1800.01, EXCLUDED),            # just before the preictal period
    (-1800, PREICTAL),               # preictal starts 30 min before onset
    (-600, PREICTAL),
    (-5, PREICTAL),                  # preictal ends 5 s before onset
    (-4.99, EXCLUDED),               # the 5 s gap
    (-0.01, EXCLUDED),
    (0, ICTAL),                      # onset
    (60, ICTAL),                     # offset
    (60.01, EXCLUDED),               # just after the seizure
    (60 + 4 * H - 0.01, EXCLUDED),   # just inside 4 h after offset
    (60 + 4 * H, INTERICTAL),        # exactly 4 h after offset
])
def test_single_seizure_boundaries(single, dt, expected):
    assert lab(single, 5 * H + dt) == expected


def test_windows_are_labeled_by_end_time(single):
    starts, labels = window_labels(single.placed[0], single, R, length_s=30, step_s=5)
    onset = 5 * H
    by_end = dict(zip(starts + 30, labels))
    assert by_end[onset - 5] == PREICTAL        # window ending 5 s before onset
    assert by_end[onset] == ICTAL                # window ending at onset
    assert by_end[onset - 1800] == PREICTAL
    assert by_end[onset - 1805] == EXCLUDED


def test_windows_at_other_lengths(single):
    for length, step in [(10, 5), (30, 5), (60, 10)]:
        starts, labels = window_labels(single.placed[0], single, R, length, step)
        assert starts[-1] + length <= 10 * H < starts[-1] + length + step
        expected = labels_at(starts + length, single, R)
        assert np.array_equal(labels, expected)


def test_interval_durations_add_up(single):
    ivals = label_intervals(single.placed[0], single, R)
    assert ivals[0][0] == 0 and ivals[-1][1] == 10 * H
    assert all(a[1] == b[0] for a, b in zip(ivals, ivals[1:]))
    assert sum(b - a for a, b, _ in ivals) == pytest.approx(10 * H)
    names = [x[2] for x in ivals]
    assert names == ["interictal", "excluded", "preictal", "excluded", "ictal", "excluded", "interictal"]


# ---------------------------------------------------------------- merging and eligibility

def test_close_seizures_merge_into_one_event():
    s1, s2, s3 = (5 * H, 5 * H + 60), (5 * H + 1060, 5 * H + 1100), (8 * H, 8 * H + 30)
    (tl,) = timelines([rec("PN00-1.edf", seizures=[s1, s2, s3])], {"PN00-1.edf": (0, 12 * H)})
    assert [e.n_seizures for e in tl.events] == [2, 1]
    assert lab(tl, s2[0] - 300) == EXCLUDED      # before the 2nd seizure: not a new preictal period
    assert lab(tl, s2[0] + 10) == ICTAL          # but the 2nd seizure itself is ictal
    assert lab(tl, s3[0] - 600) == PREICTAL      # 3rd seizure is its own event (gap > 30 min)


@pytest.mark.parametrize("onset, eligible", [(1621.0, True), (1619.0, False), (600.0, False)])
def test_preictal_coverage_rule(onset, eligible):
    # recording starts at the file start, so only (onset - 5) s of the 1795 s preictal period is recorded
    (tl,) = timelines([rec("PN00-1.edf", seizures=[(onset, onset + 30)])], {"PN00-1.edf": (0, 3 * H)})
    assert tl.events[0].eligible is eligible
    assert lab(tl, onset - 60) == (PREICTAL if eligible else EXCLUDED)


# ---------------------------------------------------------------- timelines across files

def test_preictal_period_continues_into_previous_file():
    a, b = rec("PN00-1.edf"), rec("PN00-2.edf", seizures=[(300, 360)])
    info = {"PN00-1.edf": (0, H), "PN00-2.edf": (H + 10, 2 * H)}
    (tl,) = timelines([a, b], info)
    assert tl.events[0].eligible
    pa = tl.placed[0]
    assert lab(tl, pa.start + 3000) == PREICTAL             # end of the previous file
    starts, labels = window_labels(pa, tl, R, 30, 5)
    assert (labels == PREICTAL).any()


def test_recording_after_midnight_goes_on_next_day():
    a, b = rec("PN00-1.edf"), rec("PN00-2.edf", seizures=[(100, 160)])
    info = {"PN00-1.edf": (23 * H, H), "PN00-2.edf": (10, H)}
    (tl,) = timelines([a, b], info)
    assert tl.placed[1].start == 24 * H + 10
    assert tl.events[0].eligible


def test_small_overlap_is_not_pushed_to_next_day():
    a, b = rec("PN00-1.edf"), rec("PN00-2.edf")
    info = {"PN00-1.edf": (10 * H, H), "PN00-2.edf": (10.5 * H, H)}
    (tl,) = timelines([a, b], info)
    assert tl.placed[1].start == 10.5 * H
    assert any("overlaps" in n for n in tl.notes)


def test_neighbouring_file_seizure_blocks_interictal():
    a, b = rec("PN00-1.edf"), rec("PN00-2.edf", seizures=[(600, 660)])
    info = {"PN00-1.edf": (0, H), "PN00-2.edf": (H, H)}
    (tl,) = timelines([a, b], info)
    assert lab(tl, 100) == EXCLUDED     # < 4 h before a seizure in the next file


# ---------------------------------------------------------------- TUSZ rules (D-5)

def test_tusz_seizure_free_session_is_interictal():
    s1 = rec("aaaaaaac_s001_t000.edf", seizures=[(600, 660)], dataset="tusz", patient="aaaaaaac")
    s2 = rec("aaaaaaac_s002_t000.edf", dataset="tusz", patient="aaaaaaac")
    tls = timelines([s1, s2], {s1.rel_path: (9 * H, H), s2.rel_path: (9 * H, H)})
    free = next(t for t in tls if t.key[2] == "s002")
    assert free.role == "train_test"
    assert lab(free, free.placed[0].start + 100) == INTERICTAL


def test_tusz_file_without_start_time_is_never_interictal():
    t0 = rec("aaaaaaac_s001_t000.edf", seizures=[(600, 660)], dataset="tusz", patient="aaaaaaac")
    t1 = rec("aaaaaaac_s001_t001.edf", dataset="tusz", patient="aaaaaaac")
    tls = timelines([t0, t1], {t0.rel_path: (9 * H, H), t1.rel_path: (None, 10 * H)})
    alone = next(t for t in tls if any(p.rec is t1 for p in t.placed))
    assert not alone.allow_interictal
    starts, labels = window_labels(alone.placed[0], alone, R, 30, 5)
    assert (labels == EXCLUDED).all()


def test_tusz_patient_without_seizures_is_false_alarm_only():
    r = rec("aaaaaaaz_s001_t000.edf", dataset="tusz", patient="aaaaaaaz")
    (tl,) = timelines([r], {r.rel_path: (9 * H, H)})
    assert tl.role == "false_alarm_only"
    assert lab(tl, tl.placed[0].start + 100) == INTERICTAL


def test_mental_arithmetic_is_false_alarm_only():
    r = rec("Subject00_1.edf", dataset="mental_arith", patient="Subject00")
    (tl,) = timelines([r], {r.rel_path: (9 * H, 180)})
    assert tl.role == "false_alarm_only"


# ---------------------------------------------------------------- excluded seizures (F-11)

def test_excluded_seizure_still_blocks_interictal():
    r = rec("PN00-1.edf", excluded=[(5 * H, 5 * H)])
    (tl,) = timelines([r], {"PN00-1.edf": (0, 10 * H)})
    assert tl.events == []
    assert lab(tl, 5 * H - 600) == EXCLUDED      # not preictal, not interictal
    assert lab(tl, 5 * H + 3 * H) == EXCLUDED
    assert lab(tl, 0.5 * H) == INTERICTAL        # more than 4 h away


# ---------------------------------------------------------------- subjects

def test_chb21_is_its_own_timeline_but_same_subject():
    a = rec("chb01_01.edf", seizures=[(2996, 3036)], dataset="chbmit", patient="chb01")
    b = rec("chb21_01.edf", dataset="chbmit", patient="chb21")
    b.subject = "chbmit:chb01"
    tls = timelines([a, b], {a.rel_path: (0, H), b.rel_path: (0, H)})
    assert len(tls) == 2 and {t.subject for t in tls} == {"chbmit:chb01"}

"""SeizeIT2 adapter (evaluation methods v1.13 Section 11.5 and v1.15)."""

import numpy as np
import pytest

from conftest import write_edf
from preictal.data.labels import EXCLUDED, ICTAL, INTERICTAL, PREICTAL, LabelRules
from preictal.data.seizeit2 import (
    CHANNELS, discover_patient, read_seizures, recording_features, timeline, window_labels,
)
from preictal.features.build_features import pool

FS = 250
HEADER = "onset\tduration\teventType\tlateralization\tlocalization\tvigilance\tconfidence\tchannels\tdateTime\trecordingDuration\n"


def make_patient(root, sub, runs, channels=CHANNELS):
    """runs: list of (duration_s, [(onset, duration, eventType), ...])."""
    rng = np.random.default_rng(0)
    d = root / sub / "ses-01" / "eeg"
    for k, (dur, events) in enumerate(runs, start=1):
        stem = f"{sub}_ses-01_task-szMonitoring_run-{k:02d}"
        write_edf(d / f"{stem}_eeg.edf", list(channels), [np.round(rng.normal(0, 20, int(dur * FS))) for _ in channels],
                  FS, start_time="00.00.00")
        rows = "".join(f"{on}\t{du}\t{ty}\tleft\tn/a\tn/a\tn/a\tn/a\t2000-01-01 00:00:00\t{dur}\n" for on, du, ty in events)
        (d / f"{stem}_events.tsv").write_text(HEADER + f"0\t{dur}\tbckg\tn/a\tn/a\tn/a\tn/a\tn/a\t2000-01-01 00:00:00\t{dur}\n" + rows)
    return root


@pytest.fixture
def rules():
    return LabelRules(preictal_start_s=1800, sph_s=5, interictal_gap_s=4 * 3600, merge_gap_s=1800, min_coverage=0.9)


def test_only_sz_rows_are_seizures(tmp_path):
    f = tmp_path / "e.tsv"
    f.write_text(HEADER + "0\t60\tbckg\tn/a\tn/a\tn/a\tn/a\tn/a\tx\t60\n10\t5\tsz_foc_ia\tl\tn/a\tn/a\tn/a\tn/a\tx\t60\n"
                 "20\t2\timpd\tn/a\tn/a\tn/a\tn/a\tn/a\tx\t60\n")
    assert read_seizures(f) == [(10.0, 15.0)]


def test_files_in_run_order_and_back_to_back(tmp_path):
    root = tmp_path / "seizeit2_v1.1.0"
    make_patient(root, "sub-001", [(600, []), (900, []), (300, [])])
    p = discover_patient(root, "sub-001")
    assert [r.rel_path.split("run-")[1][:2] for r in p.recordings] == ["01", "02", "03"]
    tl = timeline(p, LabelRules())
    assert [(pl.start, pl.duration) for pl in tl.placed] == [(0, 600), (600, 900), (1500, 300)]


def test_preictal_only_inside_the_seizure_file(tmp_path, rules):
    root = tmp_path / "seizeit2_v1.1.0"
    # seizure A 10 min into run 2 (its lead-up is mostly in run 1: not eligible);
    # seizure B 40 min into run 4 (whole lead-up inside run 4: eligible)
    make_patient(root, "sub-001", [(3600, []), (3600, [(600, 30, "sz_foc_a")]), (6 * 3600, []),
                                   (3600, [(2400, 30, "sz_foc_ia")])])
    tl = timeline(discover_patient(root, "sub-001"), rules)
    a, b = tl.events
    assert not a.eligible and b.eligible
    labs = [window_labels(p, tl, rules, 30, 5) for p in tl.placed]
    assert not (labs[0][1] == PREICTAL).any()                       # no cross-file lead-up
    assert not (labs[1][1] == PREICTAL).any()                       # A is ineligible
    s4, l4 = labs[3]
    pre = s4[l4 == PREICTAL] + 30
    assert len(pre) and pre.min() >= 2400 - 1800 and pre.max() <= 2400 - 5
    assert (labs[1][1] == ICTAL).any()


def test_interictal_uses_chained_distances(tmp_path, rules):
    root = tmp_path / "seizeit2_v1.1.0"
    make_patient(root, "sub-001", [(3600, []), (3 * 3600, [(1800, 60, "sz_foc_a")]), (6 * 3600, [])])
    tl = timeline(discover_patient(root, "sub-001"), rules)
    on = tl.seizures[0][0]
    for p in tl.placed:
        s, l = window_labels(p, tl, rules, 30, 5)
        t_end = p.start + s + 30
        inter = t_end[l == INTERICTAL]
        assert np.all((inter <= on - 4 * 3600) | (inter >= tl.seizures[0][1] + 4 * 3600))
    s, l = window_labels(tl.placed[0], tl, rules, 30, 5)
    assert not (l == INTERICTAL).any()                              # run 1 ends 30 min before the seizure


def test_features_on_behind_the_ear_channels(tmp_path):
    root = tmp_path / "seizeit2_v1.1.0"
    make_patient(root, "sub-002", [(300, [])])
    p = discover_patient(root, "sub-002").recordings[0]
    starts = np.arange(0, 300 - 30 + 1e-9, 5.0)
    f, c, present = recording_features(p.path, starts, 30)
    assert f.shape == (len(starts), 3, 19) and c.shape == (len(starts), 12) and present.all()
    assert not np.isnan(f).any() and not np.isnan(c[starts >= 10]).any()
    assert pool(f).shape == (len(starts), 76)
    f2, c2, _ = recording_features(p.path, starts, 30, chunk_windows=7)
    assert np.allclose(f, f2, rtol=1e-4, atol=1e-4)


def test_two_channel_layout_has_no_cross_channel(tmp_path):
    root = tmp_path / "seizeit2_v1.1.0"
    make_patient(root, "sub-003", [(200, [])], channels=("BTEleft SD", "BTEright SD"))
    p = discover_patient(root, "sub-003").recordings[0]
    f, c, present = recording_features(p.path, np.arange(0, 170, 5.0), 30)
    assert present.tolist() == [True, True, False]
    assert np.isnan(f[:, 2, :]).all() and not np.isnan(c[5:, 3]).any()   # homologous pair present

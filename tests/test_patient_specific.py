"""Patient-specific test folds (docs/evaluation_methods.md v1.3, Section 11)."""

import numpy as np

from preictal.data.labels import EXCLUDED, ICTAL, INTERICTAL, PREICTAL
from preictal.evaluation.patient_specific import patient_folds

H = 3600.0


def timeline(onsets, hours=48, step=5.0):
    """One patient, one timeline, labeled like the real rules (simplified)."""
    t = np.arange(30, hours * H, step)
    lab = np.full(len(t), EXCLUDED, dtype=np.int8)
    far = np.ones(len(t), bool)
    for on in onsets:
        far &= (t <= on - 4 * H) | (t >= on + 60 + 4 * H)
        lab[(t >= on - 1800) & (t <= on - 5)] = PREICTAL
        lab[(t >= on) & (t <= on + 60)] = ICTAL
    lab[far & (lab == EXCLUDED)] = INTERICTAL
    return t, lab, np.zeros(len(t), dtype=np.int32)


def test_one_fold_per_seizure_with_no_overlap():
    onsets = [10 * H, 22 * H, 36 * H]
    t, lab, tl = timeline(onsets)
    folds = list(patient_folds(t, lab, tl, [(0, o) for o in onsets]))
    assert len(folds) == 3
    all_test = []
    for i, train, test in folds:
        assert not set(train) & set(test)
        on = onsets[i]
        assert (lab[test] == PREICTAL).sum() > 0 and (lab[test] == INTERICTAL).sum() > 0
        assert np.all(np.abs(t[train] - on) > 4 * H)                  # nothing near the test seizure
        assert (lab[train] == PREICTAL).sum() > 0                      # other seizures still train
        pre = test[lab[test] == PREICTAL]
        assert np.all((t[pre] >= on - 1800) & (t[pre] <= on - 5))
        all_test += list(test[lab[test] == INTERICTAL])
    assert sorted(all_test) == sorted(np.flatnonzero(lab == INTERICTAL))   # every interictal window tested once


def test_interictal_chunk_has_a_buffer():
    onsets = [10 * H, 30 * H]
    t, lab, tl = timeline(onsets)
    for i, train, test in patient_folds(t, lab, tl, [(0, o) for o in onsets]):
        chunk = test[lab[test] == INTERICTAL]
        lo, hi = t[chunk].min(), t[chunk].max()
        tr = t[train]
        assert not np.any((tr >= lo - 300) & (tr <= hi + 300))


def test_other_timelines_are_not_excluded():
    t1, l1, _ = timeline([10 * H], hours=24)
    t2, l2, _ = timeline([12 * H], hours=24)
    t, lab = np.concatenate([t1, t2]), np.concatenate([l1, l2])
    tl = np.concatenate([np.zeros(len(t1), int), np.ones(len(t2), int)])
    (_, train, test), _ = list(patient_folds(t, lab, tl, [(0, 10 * H), (1, 12 * H)]))
    # the second timeline's seizure (same clock time range) is still available for training
    assert ((tl[train] == 1) & (lab[train] == PREICTAL)).any()

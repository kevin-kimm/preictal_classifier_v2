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


def test_blend_weights_give_the_person_half_of_each_class():
    from preictal.models.train import blend_weights
    rng = np.random.default_rng(0)
    yg = rng.choice([PREICTAL, ICTAL, INTERICTAL], size=5000, p=[0.1, 0.02, 0.88])
    sg = rng.integers(0, 20, 5000)
    yp = rng.choice([PREICTAL, ICTAL, INTERICTAL], size=300, p=[0.2, 0.05, 0.75])
    wg, wp = blend_weights(yg, sg, yp, personal_share=0.5)
    for c in (PREICTAL, ICTAL, INTERICTAL):
        share = wp[yp == c].sum() / (wp[yp == c].sum() + wg[yg == c].sum())
        assert abs(share - 0.5) < 1e-9


def test_inner_interictal_folds_hold_out_each_chunk_with_a_gap():
    from preictal.evaluation.patient_specific import inner_interictal_folds
    onsets = [10 * H, 30 * H, 44 * H]
    t, lab, tl = timeline(onsets, hours=60)
    _, train, _ = next(iter(patient_folds(t, lab, tl, [(0, o) for o in onsets])))
    held = []
    for inner_train, chunk in inner_interictal_folds(t, lab, tl, train, k=3):
        assert set(chunk) <= set(train) and np.all(lab[chunk] == INTERICTAL)
        assert not set(inner_train) & set(chunk)
        lo, hi = t[chunk].min(), t[chunk].max()
        assert not np.any((t[inner_train] >= lo - 300) & (t[inner_train] <= hi + 300))
        assert (lab[inner_train] == PREICTAL).any()
        held += list(chunk)
    assert sorted(held) == sorted(train[lab[train] == INTERICTAL])

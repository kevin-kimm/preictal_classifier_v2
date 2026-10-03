"""Forward-in-time simulation steps (evaluation methods v1.19): nothing from the future is used."""

import numpy as np

from preictal.data.labels import EXCLUDED, ICTAL, INTERICTAL, PREICTAL
from preictal.evaluation.learning_curve import forward_steps

H = 3600.0


def labelled(onsets, hours=80, step=5.0):
    t = np.arange(30, hours * H, step)
    lab = np.full(len(t), EXCLUDED, dtype=np.int8)
    far = np.ones(len(t), bool)
    for on in onsets:
        far &= (t <= on - 4 * H) | (t >= on + 60 + 4 * H)
        lab[(t >= on - 1800) & (t <= on - 5)] = PREICTAL
        lab[(t >= on) & (t <= on + 60)] = ICTAL
    lab[far & (lab == EXCLUDED)] = INTERICTAL
    return t, lab


def test_steps_never_train_on_the_future():
    onsets = [10 * H, 22 * H, 30 * H, 50 * H]
    t, y = labelled(onsets)
    steps = forward_steps(t, y, onsets)
    assert [s.k for s in steps] == [0, 1, 2, 3]
    for s in steps:
        assert np.all(t[s.train] <= s.cutoff)                                   # nothing after retraining
        assert np.all(t[s.train][y[s.train] == INTERICTAL] <= s.cutoff - 4 * H)  # normal only once confirmable
        assert np.all(t[s.test] > s.cutoff)                                     # scored on the future only
        assert not set(s.train) & set(s.test)
        pre_train = t[s.train][y[s.train] == PREICTAL]
        assert np.all(pre_train < s.next_onset - 1800 + 1e-6) or len(pre_train) == 0
        pre_test = t[s.test][y[s.test] == PREICTAL]
        assert len(pre_test) and np.all((pre_test >= s.next_onset - 1800) & (pre_test <= s.next_onset - 5))


def test_step_zero_is_calibration_only():
    onsets = [10 * H, 30 * H]
    t, y = labelled(onsets)
    s0 = forward_steps(t, y, onsets)[0]
    assert s0.k == 0 and len(s0.train) == 0
    assert np.isclose(s0.cutoff, 6 * H, atol=31)
    assert np.all(t[s0.baseline] <= s0.cutoff) and not np.isin(y[s0.baseline], (PREICTAL, ICTAL)).any()


def test_learning_grows_step_by_step():
    onsets = [10 * H, 22 * H, 34 * H, 46 * H]
    t, y = labelled(onsets)
    steps = forward_steps(t, y, onsets)
    n_pre = [(y[s.train] == PREICTAL).sum() for s in steps]
    assert n_pre[0] == 0 and all(b > a for a, b in zip(n_pre, n_pre[1:]))


def test_early_first_seizure_skips_calibration_and_close_seizures_are_skipped():
    onsets = [1.2 * H, 1.5 * H, 20 * H]
    t, y = labelled(onsets, hours=30)
    steps = forward_steps(t, y, onsets)
    assert 0 not in [s.k for s in steps]          # too little time before the first seizure
    assert 1 not in [s.k for s in steps]          # second seizure comes before retraining

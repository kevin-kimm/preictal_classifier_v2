"""Forward-in-time simulation of a device that keeps learning its wearer (evaluation methods v1.19).

For one patient on one timeline, with eligible seizure events e_1 < e_2 < ... (onsets):

* step 0, calibration: the device has seen no seizure. Its personal baseline comes from the
  first `calib_s` of recording (all non-ictal windows, which it assumes are normal), and it
  predicts with the general model from the end of calibration until e_1.
* step k (k = 1..n-1): the device is retrained `retrain_delay_s` after e_k's onset, using only
  what it could know then: preictal and ictal windows of seizures that have already happened,
  and interictal windows that are at least `gap_s` before the retraining time (later windows
  can't yet be confirmed as normal). It then predicts from the retraining time until e_{k+1}.

Each step is scored only on its own future: the preictal windows of the next seizure against the
interictal windows in between. Nothing after a step's retraining time is ever used to train it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..data.labels import ICTAL, INTERICTAL, PREICTAL


@dataclass
class Step:
    k: int                    # seizures learned so far
    cutoff: float             # time of (re)training, on the timeline (s)
    train: np.ndarray         # personal training windows (empty at step 0)
    baseline: np.ndarray      # windows the personal baseline is computed from
    test: np.ndarray          # windows scored at this step (next seizure's preictal + interictal before it)
    next_onset: float         # the seizure this step is trying to predict


def forward_steps(t: np.ndarray, y: np.ndarray, onsets, preictal_s: float = 1800.0, sph_s: float = 5.0,
                  gap_s: float = 4 * 3600.0, calib_s: float = 6 * 3600.0, retrain_delay_s: float = 3600.0,
                  min_calib_s: float = 3600.0):
    """Steps for one patient. t: window end times; y: labels (with hindsight); onsets: eligible event onsets."""
    onsets = np.sort(np.asarray(onsets, dtype=float))
    steps = []
    if len(onsets) == 0:
        return steps
    # which event each preictal window belongs to (the first onset at or after its end time)
    owner = np.searchsorted(onsets, t, side="left")
    t0 = t.min() - 30.0                                       # start of recording (first window start)

    # step 0: calibration, then the general model until the first seizure
    cut0 = min(t0 + calib_s, onsets[0] - preictal_s)
    if cut0 - t0 >= min_calib_s:
        base = np.flatnonzero((t <= cut0) & (y != ICTAL) & (y != PREICTAL))
        test = np.flatnonzero((t > cut0) & (((y == PREICTAL) & (owner == 0)) | (y == INTERICTAL))
                              & (t <= onsets[0] - sph_s))
        steps.append(Step(0, cut0, np.array([], dtype=int), base, test, onsets[0]))

    for k in range(1, len(onsets)):
        cut = onsets[k - 1] + retrain_delay_s
        if cut >= onsets[k] - sph_s:
            continue                                          # next seizure comes before retraining
        known_pre = (y == PREICTAL) & (owner <= k - 1) & (t <= cut)
        known_ictal = (y == ICTAL) & (t <= cut)
        known_inter = (y == INTERICTAL) & (t <= cut - gap_s)
        train = np.flatnonzero(known_pre | known_ictal | known_inter)
        base = np.flatnonzero(known_inter)
        test = np.flatnonzero((t > cut) & (t <= onsets[k] - sph_s)
                              & (((y == PREICTAL) & (owner == k)) | (y == INTERICTAL)))
        steps.append(Step(k, cut, train, base, test, onsets[k]))
    return steps

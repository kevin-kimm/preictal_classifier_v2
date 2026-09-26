"""Patient-specific test (docs/evaluation_methods.md v1.3, Section 11).

Within one patient, leave one eligible seizure out at a time:

* test: the held-out seizure's preictal windows, plus one of n equal chunks of the
  patient's interictal windows (in time order), where n is the number of eligible seizures;
* training: every other preictal, ictal and interictal window of the same patient,
  except anything within 4 h of the held-out seizure's onset and anything within
  5 min of the held-out interictal chunk. The buffers keep overlapping windows and
  the minutes around the test seizure out of training.
"""

from __future__ import annotations

import numpy as np

from ..data.labels import ICTAL, INTERICTAL, PREICTAL


def patient_folds(times: np.ndarray, labels: np.ndarray, timelines: np.ndarray,
                  events: list[tuple[int, float]], preictal_s: float = 1800.0, sph_s: float = 5.0,
                  block_s: float = 4 * 3600.0, gap_s: float = 300.0):
    """Yield (event index, train indices, test indices) for one patient's windows.

    events are (timeline code, onset) pairs of the patient's eligible seizures.
    """
    events = sorted(events)
    n = len(events)
    inter = np.flatnonzero(labels == INTERICTAL)
    inter = inter[np.lexsort((times[inter], timelines[inter]))]
    chunks = np.array_split(inter, n) if n else []
    trainable = np.isin(labels, (PREICTAL, ICTAL, INTERICTAL))
    for i, (tl, onset) in enumerate(events):
        pre = np.flatnonzero((timelines == tl) & (labels == PREICTAL)
                             & (times >= onset - preictal_s) & (times <= onset - sph_s))
        chunk = chunks[i]
        excluded = (timelines == tl) & (times >= onset - block_s) & (times <= onset + block_s)
        for code in np.unique(timelines[chunk]):
            t = times[chunk][timelines[chunk] == code]
            excluded |= (timelines == code) & (times >= t.min() - gap_s) & (times <= t.max() + gap_s)
        train = np.flatnonzero(trainable & ~excluded)
        test = np.concatenate([pre, chunk])
        yield i, train, test

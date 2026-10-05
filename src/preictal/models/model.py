"""Montage-agnostic classifier (REQ-M1).

D1 baseline (docs/evaluation_methods.md, Section 5): gradient boosting on the
60 pooled features, which are computed from whatever derivations are present.
Three classes; the risk score is the probability of preictal.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from ..data.labels import ICTAL, INTERICTAL, PREICTAL

CLASS_ORDER = (PREICTAL, ICTAL, INTERICTAL)


def build_model(seed: int) -> HistGradientBoostingClassifier:
    """scikit-learn defaults, with the seed as random_state (pre-registered, not tuned)."""
    return HistGradientBoostingClassifier(random_state=seed)


def predict_proba(model, X: np.ndarray) -> np.ndarray:
    """Class probabilities as columns (preictal, ictal, interictal)."""
    raw = model.predict_proba(X)
    out = np.zeros((len(X), len(CLASS_ORDER)))
    for j, c in enumerate(model.classes_):
        out[:, CLASS_ORDER.index(int(c))] = raw[:, j]
    return out


class ColumnSubsetModel:
    """A fitted model that only sees some columns; used for models trained on one patient's data.

    Columns with fewer than two distinct (non-missing) values in the training data carry no
    information, and some scikit-learn versions fail on them (e.g. a channel pair a patient
    doesn't have). They are dropped for training and for prediction alike.
    """

    def __init__(self, model, keep: np.ndarray):
        self.model, self.keep = model, keep
        self.classes_ = model.classes_

    def predict_proba(self, X):
        return self.model.predict_proba(np.asarray(X)[:, self.keep])


def informative_columns(X: np.ndarray) -> np.ndarray:
    """True for columns with at least two distinct non-missing values."""
    keep = np.zeros(X.shape[1], dtype=bool)
    for j in range(X.shape[1]):
        col = X[:, j]
        col = col[~np.isnan(col)]
        keep[j] = col.size > 1 and np.nanmax(col) > np.nanmin(col)
    return keep


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

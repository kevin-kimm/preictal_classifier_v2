"""Model helpers."""

import numpy as np


def test_column_subset_model_drops_empty_and_constant_columns():
    from preictal.models.model import ColumnSubsetModel, build_model, informative_columns, predict_proba
    rng = np.random.default_rng(0)
    X = rng.normal(size=(400, 5))
    y = np.where(X[:, 0] > 0, 0, 2)
    X[:, 1] = np.nan                       # a channel pair this patient doesn't have
    X[:, 3] = 7.0                          # constant
    keep = informative_columns(X)
    assert keep.tolist() == [True, False, True, False, True]
    m = ColumnSubsetModel(build_model(0).fit(X[:, keep], y), keep)
    p = predict_proba(m, X)
    assert p.shape == (400, 3) and np.allclose(p.sum(axis=1), 1)

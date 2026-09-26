"""D2 feature transforms (docs/evaluation_methods.md, Section 10)."""

import numpy as np
import pytest

from preictal.features.transforms import (
    clock_features, context_features, rolling_normalize, timeline_has_clock,
)

STEP = 5.0


def series(n, tl=0, seed=0):
    rng = np.random.default_rng(seed)
    return rng.normal(size=(n, 2)), np.full(n, tl), np.arange(n) * STEP + 30


def test_normalization_matches_manual_median_and_iqr():
    X, tl, t = series(800)
    Z = rolling_normalize(X, tl, t)
    i = 700
    past = X[(t > t[i] - 1800) & (t <= t[i])]
    q25, q50, q75 = np.percentile(past, [25, 50, 75], axis=0)
    assert np.allclose(Z[i], (X[i] - q50) / (q75 - q25), atol=1e-4)


def test_normalization_needs_one_minute_and_is_causal():
    X, tl, t = series(400)
    Z = rolling_normalize(X, tl, t)
    assert np.isnan(Z[:11]).all() and not np.isnan(Z[11]).any()
    X2 = X.copy()
    X2[300:] += 100                       # change the future
    assert np.allclose(rolling_normalize(X2, tl, t)[:300], Z[:300], equal_nan=True)


def test_timelines_are_kept_apart_and_row_order_does_not_matter():
    Xa, tla, ta = series(200, tl=0, seed=1)
    Xb, tlb, tb = series(200, tl=1, seed=2)
    X, tl, t = np.vstack([Xa, Xb]), np.concatenate([tla, tlb]), np.concatenate([ta, tb])
    Z = rolling_normalize(X, tl, t)
    assert np.allclose(Z[:200], rolling_normalize(Xa, tla, ta), equal_nan=True)
    perm = np.random.default_rng(3).permutation(400)
    assert np.allclose(rolling_normalize(X[perm], tl[perm], t[perm]), Z[perm], equal_nan=True)


def test_context_mean_and_slope_on_a_ramp():
    t = np.arange(200) * STEP + 30
    X = np.column_stack([2.0 * t / 60, np.ones(200)])          # rises 2 per minute
    C = context_features(X, np.zeros(200), t, 120)
    assert C.shape == (200, 4)
    i = 150
    inside = (t > t[i] - 120) & (t <= t[i])
    assert C[i, 0] == pytest.approx(X[inside, 0].mean(), rel=1e-5)
    assert C[i, 2] == pytest.approx(2.0, rel=1e-4)               # slope per minute
    assert C[i, 3] == pytest.approx(0.0, abs=1e-6)


def test_context_ignores_missing_values():
    t = np.arange(50) * STEP + 30
    X = np.ones((50, 1))
    X[10:20] = np.nan
    C = context_features(X, np.zeros(50), t, 60)
    assert C[25, 0] == pytest.approx(1.0)


def test_clock_features():
    c = clock_features(np.array([0.0, 6 * 3600, 86400 + 12 * 3600]), np.array([True, True, False]))
    assert np.allclose(c[0], [0, 1], atol=1e-6) and np.allclose(c[1], [1, 0], atol=1e-6)
    assert np.isnan(c[2]).all()
    assert timeline_has_clock("chbmit|chb01") and not timeline_has_clock("chbmit|chb10|chbmit_v1.0.0/chb10/chb10_89.edf")
    assert not timeline_has_clock("tusz|aaaaaaac|s001") and not timeline_has_clock("mental_arith|x")

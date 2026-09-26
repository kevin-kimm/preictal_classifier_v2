"""D2 step 5 neural network: gradient check and basic behaviour."""

import numpy as np
import pytest

from preictal.models.nn import DeepSetsClassifier


def data(n=600, seed=0, extras=True):
    rng = np.random.default_rng(seed)
    pc = rng.normal(size=(n, 18, 15)).astype(np.float32)
    y = rng.integers(0, 3, n)
    pc[:, :4, 0] += (y == 0)[:, None] * 2.0          # class 0 visible on a few channels
    pc[:, :, 1] += (y == 1)[:, None] * 2.0           # class 1 visible everywhere
    pc[rng.random(n) < 0.3, 16:, :] = np.nan         # some recordings lack two derivations
    ex = rng.normal(size=(n, 3)).astype(np.float32) if extras else None
    if extras:
        ex[rng.random(n) < 0.2, 2] = np.nan
    return pc, ex, y


def test_gradients_match_finite_differences():
    pc, ex, y = data(40)
    net = DeepSetsClassifier(seed=1, hidden=5, head=6, dropout=0.0)
    x, mask, e = net._prepare(pc, ex, fit=True)
    net._init(x.shape[2], e.shape[1], np.random.default_rng(1))
    net.params_ = {k: v.astype(np.float64) for k, v in net.params_.items()}
    brng = np.random.default_rng(9)
    for k in ("b1", "b2", "c1", "c2"):      # nonzero biases, so no unit sits exactly on a ReLU kink
        net.params_[k] = brng.normal(0, 0.1, net.params_[k].shape)
    x, e = x.astype(np.float64), e.astype(np.float64)
    w = np.linspace(0.5, 1.5, len(y))
    logits, cache = net._forward(x, mask, e)
    _, dlogits = net._loss(logits, y, w)
    grads = net._backward(dlogits.astype(np.float64), cache)
    rng = np.random.default_rng(2)
    for k, p in net.params_.items():
        for _ in range(4):
            i = tuple(rng.integers(0, s) for s in p.shape)
            old = p[i]
            p[i] = old + 1e-5
            lp, _ = net._loss(net._forward(x, mask, e)[0], y, w)
            p[i] = old - 1e-5
            lm, _ = net._loss(net._forward(x, mask, e)[0], y, w)
            p[i] = old
            assert grads[k][i] == pytest.approx((lp - lm) / 2e-5, rel=1e-3, abs=1e-6), k


def test_learns_a_separable_problem():
    pc, ex, y = data(3000)
    net = DeepSetsClassifier(seed=0, epochs=10, batch_size=128).fit(pc, ex, y)
    pc_t, ex_t, y_t = data(1000, seed=5)
    p = net.predict_proba(pc_t, ex_t)
    assert p.shape == (1000, 3) and np.allclose(p.sum(axis=1), 1)
    assert (p.argmax(axis=1) == y_t).mean() > 0.8
    assert net.loss_curve_[-1] < net.loss_curve_[0]


def test_reproducible_with_a_seed():
    pc, ex, y = data(500)
    a = DeepSetsClassifier(seed=3, epochs=2).fit(pc, ex, y).predict_proba(pc, ex)
    b = DeepSetsClassifier(seed=3, epochs=2).fit(pc, ex, y).predict_proba(pc, ex)
    assert np.array_equal(a, b)


def test_works_without_extras_and_with_all_channels_missing():
    pc, _, y = data(300, extras=False)
    pc[:5] = np.nan
    net = DeepSetsClassifier(seed=0, epochs=1).fit(pc, None, y)
    p = net.predict_proba(pc, None)
    assert not np.isnan(p).any()

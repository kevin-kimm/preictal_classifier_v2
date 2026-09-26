"""D2 step 5: a small neural network on the per-channel features (docs/evaluation_methods.md v1.3).

Architecture (fixed in advance, not tuned):

    each derivation's 15 features -> shared layer 15->32 -> ReLU -> 32->32 -> ReLU
    pooled over the derivations present: mean and max                         (64)
    plus the setup's other features (context, time of day), with a 0/1 flag
    for each that is missing                                                   (2e)
    -> 64 -> ReLU -> dropout 0.2 -> 3 classes (preictal, ictal, interictal)

The same shared layer is applied to every derivation and the result is pooled, so
the network accepts any number of channels, like the gradient-boosting model.
Training: weighted cross-entropy (the same sample weights as D1), AdamW (learning
rate 0.001, weight decay 0.0001), batches of 1,024, 6 epochs, seeded initialization
and shuffling.

Written in NumPy with hand-derived gradients (checked numerically in
tests/test_nn.py). The network is small enough that a GPU isn't needed, and NumPy
keeps runs exactly reproducible and adds no dependency.
"""

from __future__ import annotations

import numpy as np

N_CLASSES = 3


def _relu(x):
    return np.maximum(x, 0.0)


class DeepSetsClassifier:
    def __init__(self, seed: int = 0, epochs: int = 6, batch_size: int = 1024, lr: float = 1e-3,
                 weight_decay: float = 1e-4, hidden: int = 32, head: int = 64, dropout: float = 0.2):
        self.seed, self.epochs, self.batch_size, self.lr = seed, epochs, batch_size, lr
        self.weight_decay, self.hidden, self.head, self.dropout = weight_decay, hidden, head, dropout
        self.classes_ = np.arange(N_CLASSES)

    # ---------------------------------------------------------------- inputs

    def _prepare(self, per_channel, extras, fit=False):
        pc = np.asarray(per_channel, dtype=np.float32)
        mask = ~np.all(np.isnan(pc), axis=2)                        # derivation present
        if fit:
            flat = pc[mask]
            self.mu_ = np.nanmean(flat, axis=0).astype(np.float32)
            sd = np.nanstd(flat, axis=0).astype(np.float32)
            self.sd_ = np.where(sd > 1e-6, sd, 1.0).astype(np.float32)
            self.n_extra_ = 0 if extras is None else extras.shape[1]
            if self.n_extra_:
                self.emu_ = np.nan_to_num(np.nanmean(extras, axis=0)).astype(np.float32)
                esd = np.nan_to_num(np.nanstd(extras, axis=0))
                self.esd_ = np.where(esd > 1e-6, esd, 1.0).astype(np.float32)
        x = np.nan_to_num((pc - self.mu_) / self.sd_).astype(np.float32)
        x[~mask] = 0.0
        if self.n_extra_:
            e = np.asarray(extras, dtype=np.float32)
            miss = np.isnan(e).astype(np.float32)
            e = np.nan_to_num((e - self.emu_) / self.esd_).astype(np.float32)
            ex = np.concatenate([e, miss], axis=1)
        else:
            ex = np.zeros((len(pc), 0), dtype=np.float32)
        return x, mask, ex

    # ---------------------------------------------------------------- network

    def _init(self, n_features, n_ex, rng):
        h, g = self.hidden, self.head
        he = lambda fan_in, shape: (rng.standard_normal(shape) * np.sqrt(2.0 / fan_in)).astype(np.float32)  # noqa: E731
        self.params_ = {
            "W1": he(n_features, (n_features, h)), "b1": np.zeros(h, np.float32),
            "W2": he(h, (h, h)), "b2": np.zeros(h, np.float32),
            "V1": he(2 * h + n_ex, (2 * h + n_ex, g)), "c1": np.zeros(g, np.float32),
            "V2": he(g, (g, N_CLASSES)), "c2": np.zeros(N_CLASSES, np.float32),
        }

    def _forward(self, x, mask, ex, drop_rng=None):
        p = self.params_
        B, C, F = x.shape
        a1 = x.reshape(B * C, F) @ p["W1"] + p["b1"]
        h1 = _relu(a1)
        a2 = h1 @ p["W2"] + p["b2"]
        h2 = _relu(a2).reshape(B, C, -1)
        m = mask.astype(np.float32)[:, :, None]
        count = np.maximum(m.sum(axis=1), 1.0)                       # B x 1
        pm = (h2 * m).sum(axis=1) / count
        masked = np.where(mask[:, :, None], h2, -np.inf)
        arg = masked.argmax(axis=1)                                   # B x h
        px = np.take_along_axis(h2, arg[:, None, :], axis=1)[:, 0, :]
        px = np.where(mask.any(axis=1)[:, None], px, 0.0)
        z = np.concatenate([pm, px, ex], axis=1)
        g1pre = z @ p["V1"] + p["c1"]
        g1 = _relu(g1pre)
        keep = None
        if drop_rng is not None and self.dropout > 0:
            keep = (drop_rng.random(g1.shape) >= self.dropout).astype(np.float32) / (1 - self.dropout)
            g1 = g1 * keep
        logits = g1 @ p["V2"] + p["c2"]
        cache = (x, a1, h1, a2, m, count, arg, mask, z, g1pre, g1, keep)
        return logits, cache

    def _backward(self, dlogits, cache):
        p = self.params_
        x, a1, h1, a2, m, count, arg, mask, z, g1pre, g1, keep = cache
        B, C, F = x.shape
        h = self.hidden
        grads = {"V2": g1.T @ dlogits, "c2": dlogits.sum(axis=0)}
        dg1 = dlogits @ p["V2"].T
        if keep is not None:
            dg1 = dg1 * keep
        dg1pre = dg1 * (g1pre > 0)
        grads["V1"] = z.T @ dg1pre
        grads["c1"] = dg1pre.sum(axis=0)
        dz = dg1pre @ p["V1"].T
        dpm, dpx = dz[:, :h], dz[:, h:2 * h]
        dh2 = dpm[:, None, :] * m / count[:, :, None]
        dpx = np.where(mask.any(axis=1)[:, None], dpx, 0.0)
        np.put_along_axis(dh2, arg[:, None, :], np.take_along_axis(dh2, arg[:, None, :], axis=1) + dpx[:, None, :],
                          axis=1)
        da2 = dh2.reshape(B * C, h) * (a2 > 0)
        grads["W2"] = h1.T @ da2
        grads["b2"] = da2.sum(axis=0)
        da1 = (da2 @ p["W2"].T) * (a1 > 0)
        grads["W1"] = x.reshape(B * C, F).T @ da1
        grads["b1"] = da1.sum(axis=0)
        return grads

    @staticmethod
    def _loss(logits, y, w):
        z = logits - logits.max(axis=1, keepdims=True)
        prob = np.exp(z)
        prob /= prob.sum(axis=1, keepdims=True)
        wn = w / w.sum()
        loss = float(-(wn * np.log(prob[np.arange(len(y)), y] + 1e-12)).sum())
        d = prob.copy()
        d[np.arange(len(y)), y] -= 1.0
        return loss, (d * wn[:, None]).astype(np.float32)

    # ---------------------------------------------------------------- public API

    def fit(self, per_channel, extras, y, sample_weight=None):
        rng = np.random.default_rng(self.seed)
        x, mask, ex = self._prepare(per_channel, extras, fit=True)
        y = np.asarray(y, dtype=np.int64)
        w = np.ones(len(y), np.float32) if sample_weight is None else np.asarray(sample_weight, np.float32)
        self._init(x.shape[2], ex.shape[1], rng)
        m_ = {k: np.zeros_like(v) for k, v in self.params_.items()}
        v_ = {k: np.zeros_like(v) for k, v in self.params_.items()}
        b1, b2, eps, t = 0.9, 0.999, 1e-8, 0
        self.loss_curve_ = []
        for _ in range(self.epochs):
            order = rng.permutation(len(y))
            total = 0.0
            for s in range(0, len(y), self.batch_size):
                idx = order[s:s + self.batch_size]
                logits, cache = self._forward(x[idx], mask[idx], ex[idx], drop_rng=rng)
                loss, dlogits = self._loss(logits, y[idx], w[idx])
                grads = self._backward(dlogits, cache)
                t += 1
                for k, g in grads.items():
                    m_[k] = b1 * m_[k] + (1 - b1) * g
                    v_[k] = b2 * v_[k] + (1 - b2) * g * g
                    mh, vh = m_[k] / (1 - b1 ** t), v_[k] / (1 - b2 ** t)
                    decay = self.weight_decay * self.params_[k] if k in ("W1", "W2", "V1", "V2") else 0.0
                    self.params_[k] = (self.params_[k] - self.lr * (mh / (np.sqrt(vh) + eps) + decay)).astype(np.float32)
                total += loss * len(idx)
            self.loss_curve_.append(total / len(y))
        return self

    def predict_proba(self, per_channel, extras=None, batch_size: int = 8192) -> np.ndarray:
        """Probabilities as columns (preictal, ictal, interictal)."""
        x, mask, ex = self._prepare(per_channel, extras)
        out = np.empty((len(x), N_CLASSES), dtype=np.float64)
        for s in range(0, len(x), batch_size):
            logits, _ = self._forward(x[s:s + batch_size], mask[s:s + batch_size], ex[s:s + batch_size])
            z = logits - logits.max(axis=1, keepdims=True)
            e = np.exp(z)
            out[s:s + batch_size] = e / e.sum(axis=1, keepdims=True)
        return out

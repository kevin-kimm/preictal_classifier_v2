"""Infra-slow features (docs/evaluation_methods.md v1.25, Section 14.7; the instructor's comment on window length).

The frozen features describe 0.5-45 Hz within each 30 s window. Infra-slow activity (below 0.5 Hz) needs a
longer look: here, the 5 minutes ending at each window's end (causal: nothing after the window is used).

For every derivation:
    1. a causal low-pass filter (4th-order Butterworth, 3 Hz) and decimation to 8 Hz;
    2. power spectra of 100 s Hann segments (0.01 Hz resolution), 5 per look-back (start every 50 s);
    3. three numbers: log10 power at 0.01-0.1 Hz, log10 power at 0.1-0.5 Hz, and log10 of the infra-slow
       power (0.01-0.5 Hz) relative to 0.5-2 Hz.
They are pooled over the derivations present by mean, standard deviation, minimum and maximum, as the
frozen features are (12 numbers). Windows without 5 minutes of recording before their end get NaN.

Whether a dataset recorded infra-slow activity at all depends on its amplifiers' high-pass filters;
scripts/check_infraslow.py looks at that first.
"""

from __future__ import annotations

import warnings

import numpy as np
from scipy.signal import butter, get_window, sosfilt

DECIM_FS = 8.0
LOOKBACK_S = 300.0
SEG_S = 100.0
SEG_HOP_S = 50.0
SLOW_BANDS = {"iso_low": (0.01, 0.1), "iso_high": (0.1, 0.5)}
REF_BAND = (0.5, 2.0)
SLOW_FEATURES = ["log_iso_low", "log_iso_high", "log_iso_rel"]
POOLED_SLOW = [f"{s}_{f}" for f in SLOW_FEATURES for s in ("mean", "std", "min", "max")]
SLOW_VERSION = "slow-v1"
LEAD_S = LOOKBACK_S + 60.0          # read this much before the first window end (filter warm-up included)
EPS = 1e-12


def decimate_causal(x: np.ndarray, fs: float, target_fs: float = DECIM_FS) -> np.ndarray:
    """Causal anti-alias low-pass (3 Hz) and integer decimation; rows are channels (NaN rows stay NaN)."""
    k = int(round(fs / target_fs))
    if abs(fs / k - target_fs) > 1e-6:
        raise ValueError(f"sampling rate {fs} isn't a multiple of {target_fs}")
    sos = butter(4, 3.0, btype="low", fs=fs, output="sos")
    out = np.full((x.shape[0], x.shape[1] // k), np.nan)
    for c in range(x.shape[0]):
        if np.all(np.isnan(x[c])):
            continue
        xc = np.nan_to_num(x[c] - np.nanmean(x[c]))
        out[c] = sosfilt(sos, xc)[::k][: out.shape[1]]
    return out


def slow_channel_features(x8: np.ndarray, t0: float, ends: np.ndarray) -> np.ndarray:
    """Features (len(ends) x 3) for one decimated channel starting at time t0 (s); ends are window ends (s)."""
    fs = DECIM_FS
    seg = int(round(SEG_S * fs))
    w = get_window("hann", seg)
    freqs = np.fft.rfftfreq(seg, 1 / fs)
    masks = [(freqs >= lo) & (freqs < hi) for lo, hi in SLOW_BANDS.values()]
    ref = (freqs >= REF_BAND[0]) & (freqs < REF_BAND[1])
    df = freqs[1] - freqs[0]
    out = np.full((len(ends), len(SLOW_FEATURES)), np.nan, dtype=np.float32)
    n_seg = int(round((LOOKBACK_S - SEG_S) / SEG_HOP_S)) + 1
    cache = {}
    for j, e in enumerate(ends):
        first = e - LOOKBACK_S
        if first < t0 - 1e-6:
            continue
        psds = []
        for q in range(n_seg):
            s = int(round((first + q * SEG_HOP_S - t0) * fs))
            if s + seg > len(x8):
                psds = []
                break
            if s not in cache:
                fr = x8[s:s + seg]
                if np.isnan(fr).any():
                    cache[s] = None
                else:
                    fr = (fr - fr.mean()) * w
                    p = np.abs(np.fft.rfft(fr)) ** 2 / (fs * (w ** 2).sum())
                    p[1:-1] *= 2.0
                    cache[s] = p
            if cache[s] is None:
                psds = []
                break
            psds.append(cache[s])
        if not psds:
            continue
        p = np.mean(psds, axis=0)
        lo, hi = (p[m].sum() * df for m in masks)
        r = p[ref].sum() * df
        out[j] = [np.log10(lo + EPS), np.log10(hi + EPS), np.log10((lo + hi + EPS) / (r + EPS))]
    return out


def slow_features(x: np.ndarray, fs: float, t0: float, ends: np.ndarray) -> np.ndarray:
    """Per-channel features (len(ends) x n_channels x 3) for signals x (channels x samples) starting at t0."""
    x8 = decimate_causal(x, fs)
    out = np.full((len(ends), x.shape[0], len(SLOW_FEATURES)), np.nan, dtype=np.float32)
    for c in range(x.shape[0]):
        if not np.all(np.isnan(x8[c])):
            out[:, c, :] = slow_channel_features(x8[c], t0, ends)
    return out


def pool_slow(per_channel: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        stats = [np.nanmean(per_channel, axis=1), np.nanstd(per_channel, axis=1),
                 np.nanmin(per_channel, axis=1), np.nanmax(per_channel, axis=1)]
    return np.stack(stats, axis=2).reshape(len(per_channel), -1).astype(np.float32)

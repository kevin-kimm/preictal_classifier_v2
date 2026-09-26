"""D1 baseline features (docs/evaluation_methods.md, Section 5).

For every 30 s window and every one of the 18 derivations:

    log absolute band power   delta, theta, alpha, beta, gamma      (5)
    relative band power       same bands over 0.5-45 Hz              (5)
    log line length, log variance                                    (2)
    Hjorth mobility and complexity                                   (2)
    spectral edge frequency (90% of 0.5-45 Hz power)                 (1)

Per-derivation features are stored as they are (n_windows x 18 x 15), so any
subset of channels can be pooled later without re-reading the EEG (VT-12,
channel attribution in VT-19, and the Cyton layout). pool() summarizes each
feature across the derivations present by mean, std, min and max, giving 60
numbers whatever the number of channels.

Power spectra use Welch's method: 2 s Hann segments with 50% overlap. Because
windows start every 5 s, segment spectra are computed once on a 1 s grid and
averaged per window, which gives exactly the Welch estimate for each window.
"""

from __future__ import annotations

import hashlib
import json
import warnings

import numpy as np
from scipy.signal import get_window

from ..data.edf import EDFHeader
from ..data.harmonize import DERIVATIONS, harmonize

BANDS = {"delta": (0.5, 4.0), "theta": (4.0, 8.0), "alpha": (8.0, 13.0), "beta": (13.0, 30.0),
         "gamma": (30.0, 45.0)}
FEATURES = ([f"logpow_{b}" for b in BANDS] + [f"relpow_{b}" for b in BANDS]
            + ["log_line_length", "log_variance", "hjorth_mobility", "hjorth_complexity", "sef90"])
POOL_STATS = ("mean", "std", "min", "max")
POOLED_FEATURES = [f"{s}_{f}" for f in FEATURES for s in POOL_STATS]
FEATURE_VERSION = "d1-v1"
EPS = 1e-12
CYTON_DERIVATIONS = ("F7-T7", "T7-P7", "P7-O1", "F8-T8", "T8-P8", "P8-O2")


def _psd_segments(x: np.ndarray, fs: float, seg: int, hop: int, fmax: float) -> tuple[np.ndarray, np.ndarray]:
    """One-sided PSD (density, as scipy.signal.welch) of every segment on a hop grid."""
    n_seg = (len(x) - seg) // hop + 1
    frames = np.lib.stride_tricks.sliding_window_view(x, seg)[::hop][:n_seg]
    w = get_window("hann", seg)
    frames = (frames - frames.mean(axis=1, keepdims=True)) * w
    spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2 / (fs * (w ** 2).sum())
    spec[:, 1:-1] *= 2.0
    freqs = np.fft.rfftfreq(seg, 1 / fs)
    keep = freqs <= fmax + 1e-9
    return spec[:, keep], freqs[keep]


def _window_means(values: np.ndarray, starts: np.ndarray, length: int) -> np.ndarray:
    """Mean of values[s:s+length] for each start s, along axis 0, via cumulative sums."""
    c = np.concatenate([np.zeros((1,) + values.shape[1:]), np.cumsum(values, axis=0)], axis=0)
    return (c[starts + length] - c[starts]) / length


def channel_features(x: np.ndarray, fs: float, starts: np.ndarray, length: int,
                     welch_seg_s: float = 2.0) -> np.ndarray:
    """Features (n_windows x 15) for one derivation. starts/length are in samples."""
    seg = int(round(welch_seg_s * fs))
    hop = seg // 2
    if np.any(starts % hop):
        raise ValueError("window starts must fall on the Welch segment grid")
    psd, freqs = _psd_segments(x, fs, seg, hop, fmax=45.0)
    n_per_window = (length - seg) // hop + 1
    wpsd = _window_means(psd, starts // hop, n_per_window)            # n_windows x n_freq
    df = freqs[1] - freqs[0]
    band_power = np.stack([wpsd[:, (freqs >= lo) & (freqs < hi)].sum(axis=1) * df
                           for lo, hi in BANDS.values()], axis=1)
    total_mask = (freqs >= 0.5) & (freqs < 45.0)
    total = wpsd[:, total_mask].sum(axis=1) * df
    cum = np.cumsum(wpsd[:, total_mask], axis=1) * df
    with np.errstate(invalid="ignore", divide="ignore"):
        rel = band_power / total[:, None]
        sef = freqs[total_mask][np.argmax(cum >= 0.9 * total[:, None], axis=1)]
    sef = np.where(total > 0, sef, np.nan)

    # time-domain features via cumulative sums
    dx, ddx = np.diff(x), np.diff(x, 2)
    m1 = _window_means(x, starts, length)
    m2 = _window_means(x * x, starts, length)
    var = np.maximum(m2 - m1 ** 2, 0.0)
    d1 = _window_means(dx, starts, length - 1)
    d2 = _window_means(dx * dx, starts, length - 1)
    var_d = np.maximum(d2 - d1 ** 2, 0.0)
    dd1 = _window_means(ddx, starts, length - 2)
    dd2 = _window_means(ddx * ddx, starts, length - 2)
    var_dd = np.maximum(dd2 - dd1 ** 2, 0.0)
    line = _window_means(np.abs(dx), starts, length - 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mobility = np.where(var > EPS, np.sqrt(var_d / var), np.nan)
        complexity = np.where(var_d > EPS, np.sqrt(var_dd / var_d) / mobility, np.nan)

    return np.column_stack([
        np.log10(band_power + EPS), rel,
        np.log10(line + EPS), np.log10(var + EPS), mobility, complexity, sef,
    ]).astype(np.float32)


def window_features(data: np.ndarray, present: np.ndarray, fs: float, starts: np.ndarray,
                    length: int) -> np.ndarray:
    """Features (n_windows x 18 x 15) for harmonized data. Absent derivations are NaN."""
    out = np.full((len(starts), data.shape[0], len(FEATURES)), np.nan, dtype=np.float32)
    for k in range(data.shape[0]):
        if present[k]:
            out[:, k, :] = channel_features(data[k], fs, starts, length)
    return out


def recording_features(hdr: EDFHeader, starts_s: np.ndarray, length_s: float,
                       chunk_windows: int = 720) -> tuple[np.ndarray, np.ndarray]:
    """Per-derivation features for windows starting at starts_s (seconds from recording start).

    The recording is read in pieces of chunk_windows windows (one hour at a 5 s
    step), so long recordings don't need to fit in memory. Returns the features
    and the 18 presence flags.
    """
    starts_s = np.asarray(starts_s, dtype=float)
    feats = np.full((len(starts_s), len(DERIVATIONS), len(FEATURES)), np.nan, dtype=np.float32)
    present = np.zeros(len(DERIVATIONS), dtype=bool)
    for k0 in range(0, len(starts_s), chunk_windows):
        chunk = starts_s[k0:k0 + chunk_windows]
        h = harmonize(hdr, start_s=chunk[0], stop_s=chunk[-1] + length_s)
        present = h.present
        idx = np.round((chunk - h.t0) * h.fs).astype(int)
        length = int(round(length_s * h.fs))
        ok = idx + length <= h.n_samples
        if ok.any():
            feats[k0:k0 + len(chunk)][ok] = window_features(h.data, h.present, h.fs, idx[ok], length)
    return feats, present


def pool(per_channel: np.ndarray, channels: np.ndarray | None = None) -> np.ndarray:
    """Montage-agnostic summary: mean, std, min and max of each feature over channels.

    per_channel is n_windows x 18 x 15; channels optionally selects derivations
    (boolean mask or indices). Returns n_windows x 60, ordered as POOLED_FEATURES.
    """
    x = per_channel if channels is None else per_channel[:, channels, :]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        stats = [np.nanmean(x, axis=1), np.nanstd(x, axis=1), np.nanmin(x, axis=1), np.nanmax(x, axis=1)]
    return np.stack(stats, axis=2).reshape(len(x), -1).astype(np.float32)


def feature_version(cfg: dict, corrections_text: str = "") -> str:
    """Identifier of everything the stored features and labels depend on.

    Feature files made with a different version are recomputed, so changing the
    label rules, window settings, feature settings or annotation corrections can't
    silently mix old and new files.
    """
    key = json.dumps({"code": FEATURE_VERSION, "labels": cfg["labels"],
                      "windows": {k: cfg["windows"][k] for k in ("length_s", "step_s")},
                      "features": cfg["features"], "corrections": corrections_text}, sort_keys=True)
    return f"{FEATURE_VERSION}-{hashlib.sha256(key.encode()).hexdigest()[:10]}"


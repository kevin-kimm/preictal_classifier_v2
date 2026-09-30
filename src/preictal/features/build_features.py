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
from scipy.signal import butter, get_window, sosfilt

from ..data.edf import EDFHeader
from ..data.harmonize import DERIVATIONS, harmonize

BANDS = {"delta": (0.5, 4.0), "theta": (4.0, 8.0), "alpha": (8.0, 13.0), "beta": (13.0, 30.0),
         "gamma": (30.0, 45.0)}
FEATURES = ([f"logpow_{b}" for b in BANDS] + [f"relpow_{b}" for b in BANDS]
            + ["log_line_length", "log_variance", "hjorth_mobility", "hjorth_complexity", "sef90"])
POOL_STATS = ("mean", "std", "min", "max")
POOLED_FEATURES = [f"{s}_{f}" for f in FEATURES for s in POOL_STATS]
FEATURE_VERSION = "d1-v1"

# Feature set v2 (evaluation methods v1.6): 4 more features per derivation, plus
# 12 connectivity features computed across derivations.
EXTRA_FEATURES = ["spectral_entropy", "peak_frequency", "log_theta_alpha", "log_slow_fast"]
FEATURES_V2 = FEATURES + EXTRA_FEATURES
CONNECTIVITY_BANDS = {"broad": (1.0, 40.0), "theta": (4.0, 8.0), "beta": (13.0, 30.0)}
CONNECTIVITY_STATS = ("mean_abs_corr", "lambda1_fraction", "eigen_entropy", "homologous_abs_corr")
CONNECTIVITY_FEATURES = [f"{b}_{s}" for b in CONNECTIVITY_BANDS for s in CONNECTIVITY_STATS]
FEATURE_VERSION_V2 = "d2-v2"
# Known issue, kept on purpose (evaluation methods v1.14, erratum): the two frontopolar pairs are
# written "FP1"/"FP2" while derivation names use "Fp1"/"Fp2", so they never match and the homologous
# correlation uses the other 6 pairs. The frozen design was developed and evaluated this way, so it is
# not changed; tests/test_features.py pins this behaviour so development and lockbox runs stay identical.
HOMOLOGOUS = [("FP1-F7", "FP2-F8"), ("F7-T7", "F8-T8"), ("T7-P7", "T8-P8"), ("P7-O1", "P8-O2"),
              ("FP1-F3", "FP2-F4"), ("F3-C3", "F4-C4"), ("C3-P3", "C4-P4"), ("P3-O1", "P4-O2")]
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
                     welch_seg_s: float = 2.0, extra: bool = False) -> np.ndarray:
    """Features (n_windows x 15, or x 19 with extra=True) for one derivation.

    starts/length are in samples.
    """
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

    cols = [np.log10(band_power + EPS), rel, np.log10(line + EPS), np.log10(var + EPS), mobility, complexity, sef]
    if extra:
        p = wpsd[:, total_mask]
        with np.errstate(invalid="ignore", divide="ignore"):
            q = p / p.sum(axis=1, keepdims=True)
            entropy = -np.nansum(np.where(q > 0, q * np.log(q), 0.0), axis=1) / np.log(p.shape[1])
        entropy = np.where(total > 0, entropy, np.nan)
        peak = np.where(total > 0, freqs[total_mask][np.argmax(p, axis=1)], np.nan)
        d, th, al, be = band_power[:, 0], band_power[:, 1], band_power[:, 2], band_power[:, 3]
        cols += [entropy, peak, np.log10((th + EPS) / (al + EPS)), np.log10((d + th + EPS) / (al + be + EPS))]
    return np.column_stack(cols).astype(np.float32)


def window_features(data: np.ndarray, present: np.ndarray, fs: float, starts: np.ndarray,
                    length: int, extra: bool = False) -> np.ndarray:
    """Features (n_windows x 18 x 15, or 19 with extra) for harmonized data. Absent derivations are NaN."""
    n_feat = len(FEATURES_V2) if extra else len(FEATURES)
    out = np.full((len(starts), data.shape[0], n_feat), np.nan, dtype=np.float32)
    for k in range(data.shape[0]):
        if present[k]:
            out[:, k, :] = channel_features(data[k], fs, starts, length, extra=extra)
    return out


def connectivity_features(data: np.ndarray, present: np.ndarray, fs: float, starts: np.ndarray,
                          length: int, warmup: int = 0, batch: int = 64, channel_names=None,
                          homologous=None) -> np.ndarray:
    """Connectivity (n_windows x 12) across the derivations present.

    For each band (1-40, 4-8 and 13-30 Hz; causal 4th-order Butterworth filter),
    the correlation matrix of the present derivations over each window gives: the mean
    absolute correlation, the largest eigenvalue as a fraction of the number of channels,
    the normalized entropy of the eigenvalues, and the mean absolute correlation between
    left-right homologous derivations. starts are sample indices into data, which begins
    `warmup` samples before the first window so the filters can settle. channel_names and
    homologous default to the 18 derivations and HOMOLOGOUS; the SeizeIT2 adapter passes its own.
    """
    channel_names = DERIVATIONS if channel_names is None else channel_names
    homologous = HOMOLOGOUS if homologous is None else homologous
    idx = np.flatnonzero(present)
    out = np.full((len(starts), len(CONNECTIVITY_FEATURES)), np.nan, dtype=np.float32)
    if len(idx) < 2:
        return out
    names = [channel_names[i] for i in idx]
    pairs = [(names.index(a), names.index(b)) for a, b in homologous if a in names and b in names]
    k = len(idx)
    iu = np.triu_indices(k, 1)
    for bi, (lo, hi) in enumerate(CONNECTIVITY_BANDS.values()):
        sos = butter(4, [lo, hi], btype="bandpass", fs=fs, output="sos")
        x = sosfilt(sos, data[idx], axis=1)
        for b0 in range(0, len(starts), batch):
            st = starts[b0:b0 + batch]
            seg = np.stack([x[:, s:s + length] for s in st])                     # b x k x L
            seg = seg - seg.mean(axis=2, keepdims=True)
            cov = seg @ seg.transpose(0, 2, 1) / length
            sd = np.sqrt(np.clip(np.diagonal(cov, axis1=1, axis2=2), 0, None))
            with np.errstate(invalid="ignore", divide="ignore"):
                corr = cov / (sd[:, :, None] * sd[:, None, :])
            corr = np.nan_to_num(corr)
            corr[:, np.arange(k), np.arange(k)] = 1.0
            ev = np.clip(np.linalg.eigvalsh(corr), 0, None)
            pe = ev / ev.sum(axis=1, keepdims=True)
            with np.errstate(invalid="ignore", divide="ignore"):
                ent = -np.sum(np.where(pe > 0, pe * np.log(pe), 0.0), axis=1) / np.log(k)
            f = np.column_stack([
                np.abs(corr[:, iu[0], iu[1]]).mean(axis=1),
                ev.max(axis=1) / k,
                ent,
                np.abs(np.stack([corr[:, a, b] for a, b in pairs], axis=1)).mean(axis=1) if pairs
                else np.full(len(st), np.nan),
            ])
            out[b0:b0 + batch, bi * 4:(bi + 1) * 4] = f
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


def recording_features_v2(hdr: EDFHeader, starts_s: np.ndarray, length_s: float, chunk_windows: int = 720,
                          warmup_s: float = 10.0):
    """Feature set v2: per-derivation features (n x 18 x 19), connectivity (n x 12), presence flags."""
    starts_s = np.asarray(starts_s, dtype=float)
    feats = np.full((len(starts_s), len(DERIVATIONS), len(FEATURES_V2)), np.nan, dtype=np.float32)
    conn = np.full((len(starts_s), len(CONNECTIVITY_FEATURES)), np.nan, dtype=np.float32)
    present = np.zeros(len(DERIVATIONS), dtype=bool)
    for k0 in range(0, len(starts_s), chunk_windows):
        chunk = starts_s[k0:k0 + chunk_windows]
        lead = min(warmup_s, chunk[0])                 # filter warm-up, where the recording allows
        lead = np.floor(lead)
        h = harmonize(hdr, start_s=chunk[0] - lead, stop_s=chunk[-1] + length_s)
        present = h.present
        idx = np.round((chunk - h.t0) * h.fs).astype(int)
        length = int(round(length_s * h.fs))
        ok = idx + length <= h.n_samples
        if ok.any():
            feats[k0:k0 + len(chunk)][ok] = window_features(h.data, h.present, h.fs, idx[ok], length, extra=True)
            conn[k0:k0 + len(chunk)][ok] = connectivity_features(h.data, h.present, h.fs, idx[ok], length)
    return feats, conn, present


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


def feature_version(cfg: dict, corrections_text: str = "", code: str = FEATURE_VERSION) -> str:
    """Identifier of everything the stored features and labels depend on.

    Feature files made with a different version are recomputed, so changing the
    label rules, window settings, feature settings or annotation corrections can't
    silently mix old and new files.
    """
    key = json.dumps({"code": code, "labels": cfg["labels"],
                      "windows": {k: cfg["windows"][k] for k in ("length_s", "step_s")},
                      "features": cfg["features"], "corrections": corrections_text}, sort_keys=True)
    return f"{code}-{hashlib.sha256(key.encode()).hexdigest()[:10]}"


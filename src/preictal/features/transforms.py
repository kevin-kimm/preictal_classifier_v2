"""D2 feature transforms (docs/evaluation_methods.md, Section 10).

All of them use only the current and earlier windows on the same timeline, so
they could run live:

normalize   each pooled feature minus its median, divided by its interquartile
            range, over the windows ending in the preceding 30 min (including
            the current one). At least 12 windows (1 min at a 5 s step) are
            needed; before that the normalized features are missing.
context     the mean and the slope (per minute) of each feature over the windows
            ending in the preceding 2, 5 or 10 min.
clock       sine and cosine of the time of day. Only CHB-MIT and Siena recordings
            placed on a timeline have real clock times; everything else is missing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

IQR_FLOOR = 1e-3


def _sorted_frame(X: np.ndarray, timeline: np.ndarray, t_end: np.ndarray):
    """Rows sorted by (timeline, time), with a time index for time-based rolling windows."""
    order = np.lexsort((t_end, timeline))
    df = pd.DataFrame(np.asarray(X, dtype=np.float64)[order], index=pd.to_datetime(t_end[order], unit="s"))
    return df, np.asarray(timeline)[order], order


def _unsort(values: np.ndarray, order: np.ndarray) -> np.ndarray:
    out = np.empty_like(values)
    out[order] = values
    return out


def _rolling(df: pd.DataFrame, groups: np.ndarray, window: str, min_periods: int):
    return df.groupby(groups, sort=True).rolling(window, min_periods=min_periods)


def rolling_normalize(X: np.ndarray, timeline: np.ndarray, t_end: np.ndarray, window_s: float = 1800.0,
                      min_windows: int = 12) -> np.ndarray:
    """Causal robust scaling of each column within each timeline."""
    df, groups, order = _sorted_frame(X, timeline, t_end)
    r = _rolling(df, groups, f"{int(window_s)}s", min_windows)
    q = {p: r.quantile(p).to_numpy() for p in (0.25, 0.5, 0.75)}
    iqr = np.maximum(q[0.75] - q[0.25], IQR_FLOOR)
    z = (df.to_numpy() - q[0.5]) / iqr
    return _unsort(z.astype(np.float32), order)


def context_features(X: np.ndarray, timeline: np.ndarray, t_end: np.ndarray, context_s: float) -> np.ndarray:
    """Mean and slope (per minute) of each column over the preceding context_s seconds.

    Returns n x (2 * d): the means, then the slopes. Missing values in a column
    are left out of that column's mean and slope.
    """
    df, groups, order = _sorted_frame(X, timeline, t_end)
    t = np.asarray(t_end, dtype=np.float64)[order]
    t = t - pd.Series(t).groupby(groups).transform("min").to_numpy()      # per-timeline origin
    vals = df.to_numpy()
    ok = ~np.isnan(vals)
    v0 = np.where(ok, vals, 0.0)
    tt = t[:, None] * ok
    frame = pd.DataFrame(np.column_stack([v0, v0 * t[:, None], tt, tt * t[:, None], ok.astype(float)]),
                         index=df.index)
    sums = _rolling(frame, groups, f"{int(context_s)}s", 1).sum().to_numpy()
    d = vals.shape[1]
    sx, stx, st, stt, n = (sums[:, k * d:(k + 1) * d] for k in range(5))
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(n > 0, sx / n, np.nan)
        denom = n * stt - st * st
        slope = np.where(denom > 1e-9, (n * stx - st * sx) / denom * 60.0, np.nan)
    return _unsort(np.column_stack([mean, slope]).astype(np.float32), order)


def clock_features(t_end: np.ndarray, has_clock: np.ndarray) -> np.ndarray:
    """Sine and cosine of the time of day; missing where the clock time isn't real."""
    hour = (np.asarray(t_end, dtype=float) % 86400) / 3600
    out = np.column_stack([np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)]).astype(np.float32)
    out[~np.asarray(has_clock, dtype=bool)] = np.nan
    return out


def timeline_has_clock(timeline_key: str) -> bool:
    """CHB-MIT and Siena timelines placed by their start times have real clock times.

    Recordings labeled on their own get a key with a third part (their file path);
    TUSZ start times are anonymized; mental arithmetic isn't used for training.
    """
    parts = timeline_key.split("|")
    return parts[0] in ("chbmit", "siena") and len(parts) == 2

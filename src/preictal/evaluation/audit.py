"""Annotation and artifact audit helpers (docs/evaluation_methods.md v1.32, Section 14.16).

Pure functions on window arrays, so they can be tested without data. Window arrays are one row per
30 s window: end time t (seconds on its timeline), timeline code tl, and per-channel RMS amplitude.
"""

from __future__ import annotations

import numpy as np

HIGH_X = 5.0          # a channel's RMS above 5 x its median on the patient's normal EEG
FLAT_X = 0.1          # a recorded channel's RMS below 0.1 x that median (electrode off, flat line)
RECENT_S = 180.0      # "recent artifact": one in the last 3 min (the alarm smoothing span)
ONSET_BEFORE_S = 300.0
ONSET_AFTER_S = 120.0
MIN_RUN = 3           # sustained: at least 3 windows in a row (15 s of new data)
FLAG_LEAD_S = 15.0    # a detection run that began at least 15 s before the annotated onset
CAND_RUN = 6          # unannotated-seizure candidate: at least 6 windows in a row (30 s)
CAND_MIN_P = 0.5      # detector threshold floor: never below 0.5
DETECTOR_PCT = 99.9   # detector threshold: this percentile of the patient's normal-EEG output


def runs(mask: np.ndarray, t: np.ndarray, tl: np.ndarray, step_s: float, min_len: int = 1) -> list[tuple[int, int]]:
    """(first, last) indices of runs of True in windows sorted by (tl, t); windows are contiguous when they
    share a timeline and are one step apart. Only runs of at least min_len windows are returned."""
    mask = np.asarray(mask, bool)
    out = []
    start = None
    for i in range(len(mask)):
        cont = (i > 0 and tl[i] == tl[i - 1] and t[i] - t[i - 1] <= 1.5 * step_s)
        if mask[i]:
            if start is None or not cont or not mask[i - 1]:
                if start is not None and i - start >= min_len:
                    out.append((start, i - 1))
                start = i
        else:
            if start is not None and i - start >= min_len:
                out.append((start, i - 1))
            start = None
    if start is not None and len(mask) - start >= min_len:
        out.append((start, len(mask) - 1))
    return out


def artifact_flags(rms: np.ndarray, ref: np.ndarray, high_x: float = HIGH_X, flat_x: float = FLAT_X):
    """Per window: (high, flat). rms is n x channels (µV, NaN where a channel is absent); ref is a boolean
    mask of the patient's normal-EEG windows, whose per-channel medians set each channel's scale."""
    rms = np.asarray(rms, float)
    with np.errstate(all="ignore"):
        med = np.nanmedian(rms[ref], axis=0) if ref.any() else np.full(rms.shape[1], np.nan)
    usable = np.isfinite(med) & (med > 0)
    if not usable.any():
        z = np.zeros(len(rms), bool)
        return z, z.copy()
    r = rms[:, usable] / med[usable]
    with np.errstate(invalid="ignore"):
        high = np.nan_to_num(r, nan=0.0).max(axis=1) > high_x
        flat = np.nan_to_num(r, nan=np.inf).min(axis=1) < flat_x
    return high, flat


def recent(flag: np.ndarray, t: np.ndarray, tl: np.ndarray, span_s: float = RECENT_S) -> np.ndarray:
    """True where any flagged window on the same timeline ends in (t - span_s, t]. Looks backwards only."""
    flag = np.asarray(flag, bool)
    out = np.zeros(len(flag), bool)
    for c in np.unique(tl):
        idx = np.flatnonzero(tl == c)
        idx = idx[np.argsort(t[idx], kind="stable")]
        tc = t[idx]
        cum = np.concatenate([[0], np.cumsum(flag[idx])])
        lo = np.searchsorted(tc, tc - span_s, side="right")
        out[idx] = cum[np.arange(1, len(idx) + 1)] - cum[lo] > 0
    return out


def onset_check(t: np.ndarray, p: np.ndarray, thr: float, onset: float, step_s: float,
                before_s: float = ONSET_BEFORE_S, after_s: float = ONSET_AFTER_S, min_run: int = MIN_RUN) -> dict:
    """For one seizure on one timeline (t sorted): is it detected (a sustained run above thr with a window
    ending within after_s of onset), and when did that run begin relative to the annotated onset?

    lead_s > 0 means the detector's run began before the annotated onset (EEG already seizure-like);
    'clipped' means the run already started before the searched span."""
    m = (t >= onset - before_s) & (t <= onset + after_s)
    idx = np.flatnonzero(m)
    res = {"detected": False, "lead_s": float("nan"), "run_start": float("nan"), "clipped": False,
           "peak": float(np.max(p[idx])) if len(idx) else float("nan")}
    if not len(idx):
        return res
    tt, pp = t[idx], p[idx]
    for a, b in runs(pp >= thr, tt, np.zeros(len(tt), int), step_s, min_run):
        if ((tt[a:b + 1] >= onset) & (tt[a:b + 1] <= onset + after_s)).any():
            res.update(detected=True, lead_s=float(onset - tt[a]), run_start=float(tt[a]), clipped=bool(a == 0))
            return res
    return res

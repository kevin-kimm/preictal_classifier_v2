"""Training data and model fitting (REQ-E2).

Feature files come from scripts/extract_features.py: one .npz per recording in
data/processed/features/<dataset>/, holding per-derivation features, labels and
window times on the recording's timeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..data.labels import ICTAL, INTERICTAL, PREICTAL
from ..features.build_features import pool
from .model import build_model

TRAIN_CLASSES = (PREICTAL, ICTAL, INTERICTAL)


def feature_file(feature_dir: Path, dataset: str, rel_path: str) -> Path:
    return Path(feature_dir) / dataset / (rel_path.replace("/", "__") + ".npz")


@dataclass
class Windows:
    per_channel: np.ndarray      # n x 18 x 15
    X: np.ndarray                # n x 60 pooled features
    y: np.ndarray                # label per window
    t_end: np.ndarray            # window end time on its timeline (s)
    subject: np.ndarray          # index into subjects
    timeline: np.ndarray         # index into timelines
    subjects: list[str]
    timelines: list[str]
    recording: np.ndarray | None = None   # index into recordings
    starts: np.ndarray | None = None      # window start within its recording (s)
    recordings: list[str] | None = None

    def rows(self, subjects: set[str]) -> np.ndarray:
        codes = [i for i, s in enumerate(self.subjects) if s in subjects]
        return np.flatnonzero(np.isin(self.subject, codes))


def load_windows(feature_dir: Path, datasets: tuple[str, ...], subjects: set[str] | None = None,
                 version: str | None = None, keep_per_channel: bool = True,
                 labels: tuple[int, ...] | None = None, every: int = 1) -> Windows:
    """Load feature files. With keep_per_channel=False only the pooled features are kept
    (per_channel is None), which saves memory. labels keeps only windows with those
    labels; every=k keeps every k-th of those windows per recording."""
    parts = {k: [] for k in ("per_channel", "conn", "X", "y", "t_end", "subject", "timeline", "recording", "starts")}
    subj_codes, tl_codes, rec_codes = {}, {}, {}
    for ds in datasets:
        for f in sorted((Path(feature_dir) / ds).glob("*.npz")):
            z = np.load(f, allow_pickle=False)
            subject = str(z["subject"])
            if subjects is not None and subject not in subjects:
                continue
            if version is not None and str(z["version"]) != version:
                raise ValueError(f"{f.name} was made by feature version {z['version']}, expected {version}; "
                                 "re-run scripts/extract_features.py")
            keep = np.ones(len(z["labels"]), dtype=bool) if labels is None else np.isin(z["labels"], labels)
            keep = np.flatnonzero(keep)[::every]
            n = len(keep)
            if n == 0:
                continue
            feats = z["features"][keep]
            conn = z["connectivity"][keep] if "connectivity" in z.files else None   # feature set v2
            if keep_per_channel:
                parts["per_channel"].append(feats)
                if conn is not None:
                    parts["conn"].append(conn)
            else:
                parts["X"].append(pool(feats) if conn is None else np.hstack([pool(feats), conn]))
            parts["y"].append(z["labels"][keep])
            parts["t_end"].append(z["t_end"][keep])
            parts["starts"].append(z["starts"][keep])
            parts["recording"].append(np.full(n, rec_codes.setdefault(str(z["recording"]), len(rec_codes)), np.int32))
            parts["subject"].append(np.full(n, subj_codes.setdefault(subject, len(subj_codes)), np.int32))
            parts["timeline"].append(np.full(n, tl_codes.setdefault(str(z["timeline"]), len(tl_codes)), np.int32))
    if not parts["y"]:
        raise FileNotFoundError(f"no feature files for {datasets} in {feature_dir}")
    if keep_per_channel:
        per_channel = np.concatenate(parts["per_channel"])
        X = pool(per_channel)
        if parts["conn"]:
            X = np.hstack([X, np.concatenate(parts["conn"])])
    else:
        per_channel, X = None, np.concatenate(parts["X"])
    return Windows(per_channel, X, np.concatenate(parts["y"]), np.concatenate(parts["t_end"]),
                   np.concatenate(parts["subject"]), np.concatenate(parts["timeline"]),
                   list(subj_codes), list(tl_codes), np.concatenate(parts["recording"]),
                   np.concatenate(parts["starts"]), list(rec_codes))


def sample_weights(y: np.ndarray, subject: np.ndarray) -> np.ndarray:
    """Each class gets equal total weight, and within a class each subject counts equally."""
    w = np.zeros(len(y))
    classes = [c for c in TRAIN_CLASSES if (y == c).any()]
    for c in classes:
        in_c = y == c
        subs, counts = np.unique(subject[in_c], return_counts=True)
        per_subject = dict(zip(subs, counts))
        w[in_c] = [1.0 / (len(classes) * len(subs) * per_subject[s]) for s in subject[in_c]]
    return w * len(y) / w.sum()


def fit(X: np.ndarray, y: np.ndarray, subject: np.ndarray, seed: int):
    keep = np.isin(y, TRAIN_CLASSES)
    model = build_model(seed)
    model.fit(X[keep], y[keep], sample_weight=sample_weights(y[keep], subject[keep]))
    return model


def blend_weights(y_general: np.ndarray, subject_general: np.ndarray, y_personal: np.ndarray,
                  personal_share: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """Weights for a general model adapted to one person (evaluation methods v1.4).

    Other patients are weighted as in D1 (each class equal, each patient equal
    within a class). The person's own windows are then scaled so that, within each
    class, they carry personal_share of the total weight.
    """
    wg = sample_weights(y_general, subject_general)
    wp = sample_weights(y_personal, np.zeros(len(y_personal), dtype=int)) if len(y_personal) else np.zeros(0)
    for c in TRAIN_CLASSES:
        g, p = y_general == c, y_personal == c
        if g.any() and p.any():
            wp[p] *= (personal_share / (1 - personal_share)) * wg[g].sum() / wp[p].sum()
    return wg, wp


def relabel(W: Windows, timelines, rules, length_s: float, step_s: float) -> np.ndarray:
    """Labels for the loaded windows under different label rules (evaluation methods v1.12).

    Used to train with a shorter interictal gap while testing with the frozen one. Only the
    interictal/excluded split can change; preictal and ictal labels must stay identical.
    """
    from ..data.labels import ICTAL, PREICTAL, window_labels
    lookup = {}
    for tl in timelines:
        for p in tl.placed:
            lookup[p.rec.rel_path] = window_labels(p, tl, rules, length_s, step_s)
    out = W.y.copy()
    for code, name in enumerate(W.recordings):
        idx = np.flatnonzero(W.recording == code)
        st, lab = lookup[name]
        pos = np.searchsorted(st, W.starts[idx])
        if np.any(pos >= len(st)) or not np.allclose(st[np.minimum(pos, len(st) - 1)], W.starts[idx]):
            raise ValueError(f"window starts of {name} don't match its labels; re-run extract_features.py")
        out[idx] = lab[pos]
    for c in (PREICTAL, ICTAL):
        if not np.array_equal(out == c, W.y == c):
            raise ValueError("relabeling changed preictal or ictal labels; only the interictal gap may change")
    return out


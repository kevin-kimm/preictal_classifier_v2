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

    def rows(self, subjects: set[str]) -> np.ndarray:
        codes = [i for i, s in enumerate(self.subjects) if s in subjects]
        return np.flatnonzero(np.isin(self.subject, codes))


def load_windows(feature_dir: Path, datasets: tuple[str, ...], subjects: set[str] | None = None,
                 version: str | None = None) -> Windows:
    parts = {k: [] for k in ("per_channel", "y", "t_end", "subject", "timeline")}
    subj_codes, tl_codes = {}, {}
    for ds in datasets:
        for f in sorted((Path(feature_dir) / ds).glob("*.npz")):
            z = np.load(f, allow_pickle=False)
            subject = str(z["subject"])
            if subjects is not None and subject not in subjects:
                continue
            if version is not None and str(z["version"]) != version:
                raise ValueError(f"{f.name} was made by feature version {z['version']}, expected {version}; "
                                 "re-run scripts/extract_features.py")
            n = len(z["labels"])
            parts["per_channel"].append(z["features"])
            parts["y"].append(z["labels"])
            parts["t_end"].append(z["t_end"])
            parts["subject"].append(np.full(n, subj_codes.setdefault(subject, len(subj_codes)), np.int32))
            parts["timeline"].append(np.full(n, tl_codes.setdefault(str(z["timeline"]), len(tl_codes)), np.int32))
    if not parts["y"]:
        raise FileNotFoundError(f"no feature files for {datasets} in {feature_dir}")
    per_channel = np.concatenate(parts["per_channel"])
    return Windows(per_channel, pool(per_channel), np.concatenate(parts["y"]), np.concatenate(parts["t_end"]),
                   np.concatenate(parts["subject"]), np.concatenate(parts["timeline"]),
                   list(subj_codes), list(tl_codes))


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

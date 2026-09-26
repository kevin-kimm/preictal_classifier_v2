"""Leave-one-patient-out folds and leakage checks (REQ-E1, REQ-E3).

docs/evaluation_methods.md, Section 3. Subjects are grouping IDs from the
loaders (chb01 and chb21 are the same subject), so a person can never be on
both sides of a split.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Fold:
    index: int
    test: str
    inner: tuple[str, ...]     # inner validation subjects (thresholds)
    train: tuple[str, ...]


@dataclass(frozen=True)
class SubjectInfo:
    dataset: str
    role: str
    eligible_test_patient: bool


def read_label_report(path: str | Path) -> dict[str, SubjectInfo]:
    with open(path, newline="") as f:
        return {r["subject"]: SubjectInfo(r["dataset"], r["role"], r["eligible_test_patient"] == "True")
                for r in csv.DictReader(f)}


def inner_size(n_candidates: int, fraction: float = 0.2, minimum: int = 2) -> int:
    return min(n_candidates, max(minimum, int(round(fraction * n_candidates))))


def draw_inner(candidates: list[str], seed: int, fold_index: int, fraction: float = 0.2,
               minimum: int = 2) -> tuple[str, ...]:
    rng = np.random.default_rng([seed, fold_index])
    k = inner_size(len(candidates), fraction, minimum)
    return tuple(sorted(rng.choice(sorted(candidates), size=k, replace=False).tolist()))


def make_folds(subjects: dict[str, SubjectInfo], datasets: tuple[str, ...], seed: int,
               fraction: float = 0.2, minimum: int = 2) -> list[Fold]:
    """One fold per eligible test patient in the training datasets."""
    pool = sorted(s for s, i in subjects.items() if i.dataset in datasets and i.role == "train_test")
    tests = [s for s in pool if subjects[s].eligible_test_patient]
    folds = []
    for k, test in enumerate(tests):
        rest = [s for s in pool if s != test]
        inner = draw_inner([s for s in rest if subjects[s].eligible_test_patient], seed, k, fraction, minimum)
        train = tuple(s for s in rest if s not in inner)
        folds.append(Fold(k, test, inner, train))
    return folds


def full_split(subjects: dict[str, SubjectInfo], datasets: tuple[str, ...], seed: int,
               fraction: float = 0.2, minimum: int = 2) -> Fold:
    """Model trained on every subject (for the false-alarm sets), with an inner set for its threshold."""
    pool = sorted(s for s, i in subjects.items() if i.dataset in datasets and i.role == "train_test")
    inner = draw_inner([s for s in pool if subjects[s].eligible_test_patient], seed, 999_999, fraction, minimum)
    return Fold(-1, "", inner, tuple(s for s in pool if s not in inner))


def check_fold(fold: Fold) -> list[str]:
    """Leakage checks for VT-08. Returns a list of problems (empty if none)."""
    problems = []
    if fold.test and fold.test in fold.train:
        problems.append(f"fold {fold.index}: test subject {fold.test} is in the training set")
    if fold.test and fold.test in fold.inner:
        problems.append(f"fold {fold.index}: test subject {fold.test} is in the inner validation set")
    overlap = set(fold.inner) & set(fold.train)
    if overlap:
        problems.append(f"fold {fold.index}: inner validation and training share {sorted(overlap)}")
    for s in (fold.test, *fold.inner, *fold.train):
        if s and ":" not in s:
            problems.append(f"fold {fold.index}: subject ID {s!r} has no dataset prefix")
    return problems

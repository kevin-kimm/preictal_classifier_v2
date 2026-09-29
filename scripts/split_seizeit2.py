"""Split SeizeIT2 into development and lockbox patients (docs/evaluation_methods.md v1.11, Section 12).

Uses only the subject folder names: 25 subjects are drawn at random (seed 0) for development;
the other 100 stay sealed as the lockbox. No seizure or recording information is read.
The split is written once to configs/seizeit2_split.yaml; the script refuses to run again
if that file exists, so the split can't be redrawn after anything is seen.

Usage, from the repo root with .venv active:
    python scripts/split_seizeit2.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "data" / "raw" / "seizeit2_v1.1.0"
OUT = REPO / "configs" / "seizeit2_split.yaml"
N_DEVELOPMENT, SEED = 25, 0


def main():
    if OUT.exists():
        sys.exit(f"{OUT} already exists; the split is fixed and is not redrawn.")
    subjects = sorted(p.name for p in ROOT.glob("sub-*") if p.is_dir())
    if len(subjects) != 125:
        sys.exit(f"expected 125 subject folders, found {len(subjects)}")
    rng = np.random.default_rng(SEED)
    dev = sorted(rng.choice(subjects, size=N_DEVELOPMENT, replace=False).tolist())
    lockbox = [s for s in subjects if s not in dev]
    OUT.write_text(
        "# SeizeIT2 split (docs/evaluation_methods.md v1.11, Section 12). Drawn once from subject IDs only.\n"
        + yaml.safe_dump({"dataset": "seizeit2_v1.1.0", "seed": SEED, "development": dev, "lockbox": lockbox},
                         sort_keys=False))
    print(f"Development: {len(dev)} subjects; lockbox: {len(lockbox)} subjects")
    print(f"Written to {OUT}")


if __name__ == "__main__":
    main()

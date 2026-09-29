"""What-if: how much normal EEG and how many testable patients for different interictal gaps.

Counts labels only; no model is trained or scored, and nothing in the frozen setup changes.
The main analysis keeps the 4 h gap (verification plan). This shows what a planned sensitivity
analysis with a shorter gap would have to work with.

Usage, from the repo root with .venv active:
    python scripts/gap_whatif.py                  gaps of 1, 2 and 4 h
    python scripts/gap_whatif.py --gaps 1 1.5 2 4
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.config import load_config  # noqa: E402
from preictal.data.labels import LabelRules, build_timelines, label_intervals  # noqa: E402
from preictal.data.loaders import discover  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gaps", type=float, nargs="+", default=[1.0, 2.0, 4.0])
    ap.add_argument("--data-root", type=Path, default=REPO / "data" / "raw")
    args = ap.parse_args()

    cfg = load_config()
    base = LabelRules.from_config(cfg)
    recs = discover(args.data_root, datasets=("chbmit", "siena"))
    print(f"{len(recs)} recordings (CHB-MIT and Siena)\n")
    print(f"{'Gap':>5} {'Dataset':8} {'Interictal h':>13} {'Excluded h':>11} {'Test patients':>14} "
          f"{'Personalized patients':>22}")
    for gap in args.gaps:
        rules = replace(base, interictal_gap_s=gap * 3600.0)
        per = defaultdict(lambda: {"eligible": 0, "interictal_h": 0.0, "excluded_h": 0.0, "dataset": ""})
        for tl in build_timelines(recs, rules):
            s = per[tl.subject]
            s["dataset"] = tl.dataset
            s["eligible"] += sum(e.eligible for e in tl.events)
            for p in tl.placed:
                for a, b, name in label_intervals(p, tl, rules):
                    if name in ("interictal", "excluded"):
                        s[f"{name}_h"] += (b - a) / 3600
        for ds in ("chbmit", "siena"):
            rows = [s for s in per.values() if s["dataset"] == ds]
            tests = sum(s["eligible"] >= 1 and s["interictal_h"] >= 1 for s in rows)
            personal = sum(s["eligible"] >= 2 and s["interictal_h"] >= 1 for s in rows)
            print(f"{gap:>4g}h {ds:8} {sum(s['interictal_h'] for s in rows):>13.1f} "
                  f"{sum(s['excluded_h'] for s in rows):>11.1f} {tests:>14} {personal:>22}")
        print()


if __name__ == "__main__":
    main()

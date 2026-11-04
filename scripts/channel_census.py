"""Which behind-the-ear channels each SeizeIT2 recording actually has.

For every EEG file: which of BTEleft / BTEright / CROSStop are in the file at all, and which of those are
flat (an electrode that was worn but gives no signal). Flat is checked on 12 one-minute samples spread over
the file: a channel counts as flat when its RMS is under 1 µV in at least 80% of them (normal EEG here is
about 10-50 µV). Headers and raw signal only; no labels, no model.

    python scripts/channel_census.py            all subjects (about a minute)
    python scripts/channel_census.py --quick    headers only, no flat check (seconds)

Output: printed tables and results/d2_plus/channel_census.md (+ a per-file CSV).
"""

from __future__ import annotations

import argparse
import csv
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.data.edf import read_header  # noqa: E402
from preictal.data.seizeit2 import CHANNELS, read_bte  # noqa: E402

ROOT = REPO / "data" / "raw" / "seizeit2_v1.1.0"
OUT = REPO / "results" / "d2_plus"
SHORT = {"BTEleft SD": "BTEleft", "BTEright SD": "BTEright", "CROSStop SD": "CROSStop"}
N_SAMPLES, SAMPLE_S, FLAT_UV, FLAT_SHARE = 12, 60.0, 1.0, 0.8


def combo(names) -> str:
    names = [SHORT[c] for c in CHANNELS if c in names]
    return " + ".join(names) if names else "(none)"


def check_file(path: Path, quick: bool):
    hdr = read_header(path)
    in_file = [c for c in CHANNELS if c in hdr.labels]
    flat = []
    if not quick and in_file and hdr.n_records > 0:
        per = max(1, int(round(SAMPLE_S / hdr.record_s)))
        starts = np.linspace(0, max(0, hdr.n_records - per), N_SAMPLES).astype(int)
        low = np.zeros(len(CHANNELS))
        for s in starts:
            x, present, _, _ = read_bte(path, int(s), per)
            with np.errstate(all="ignore"), warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                rms = np.sqrt(np.nanmean((x - np.nanmean(x, axis=1, keepdims=True)) ** 2, axis=1))
            low += present & (np.nan_to_num(rms, nan=np.inf) < FLAT_UV)
        flat = [c for j, c in enumerate(CHANNELS) if c in in_file and low[j] >= FLAT_SHARE * len(starts)]
    working = [c for c in in_file if c not in flat]
    return hdr.duration_s / 3600.0, in_file, flat, working


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="headers only, skip the flat check")
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args()

    subs = sorted(p.name for p in args.root.glob("sub-*") if p.is_dir())
    if not subs:
        sys.exit(f"No subjects under {args.root}")
    rows = []
    for k, sub in enumerate(subs, 1):
        for p in sorted((args.root / sub).glob("ses-*/eeg/*_eeg.edf")):
            try:
                hours, in_file, flat, working = check_file(p, args.quick)
            except Exception as e:  # a damaged file should not stop the count
                print(f"  {p.name}: skipped ({e})")
                continue
            rows.append(dict(subject=sub, file=p.name, hours=hours, in_file=combo(in_file),
                             flat=combo(flat) if flat else "", working=combo(working)))
        print(f"\r  {k}/{len(subs)} subjects", end="", flush=True)
    print()

    def table(key, title):
        files, hours = Counter(), defaultdict(float)
        for r in rows:
            files[r[key]] += 1
            hours[r[key]] += r["hours"]
        tot_h = sum(hours.values())
        lines = [f"### {title}", "", "| channels | files | hours | share of hours |", "|---|---:|---:|---:|"]
        for c, n in files.most_common():
            lines.append(f"| {c} | {n} | {hours[c]:.0f} | {100 * hours[c] / tot_h:.0f}% |")
        return lines

    # per patient: the set of working-channel combinations across their files
    per_sub = defaultdict(set)
    for r in rows:
        per_sub[r["subject"]].add(r["working"])
    sub_kind = Counter(" / ".join(sorted(v)) for v in per_sub.values())

    n_flat = sum(1 for r in rows if r["flat"])
    flat_by = Counter(c for r in rows if r["flat"] for c in r["flat"].split(" + "))
    md = [f"# SeizeIT2 channel census", "",
          f"{len(subs)} subjects, {len(rows)} EEG files, {sum(r['hours'] for r in rows):.0f} hours.", ""]
    md += table("in_file", "Channels present in the file") + [""]
    if not args.quick:
        md += table("working", "Channels actually working (present and not flat)") + [""]
        md += [f"Files with a worn but flat channel: {n_flat} of {len(rows)}"
               + (" (" + ", ".join(f"{c} {n}" for c, n in flat_by.most_common()) + ")" if n_flat else "") + ".", ""]
    md += ["### Patients by working-channel setup (all their files)", "", "| setup | patients |", "|---|---:|"]
    md += [f"| {k} | {n} |" for k, n in sub_kind.most_common()]
    md += ["", "Flat = RMS under 1 µV in at least 80% of 12 one-minute samples spread over the file."
           if not args.quick else "Quick mode: headers only, flat channels not checked."]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "channel_census.md").write_text("\n".join(md) + "\n")
    with open(OUT / "channel_census_files.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("\n".join(md))
    print(f"\nSaved {OUT / 'channel_census.md'} and channel_census_files.csv")


if __name__ == "__main__":
    main()

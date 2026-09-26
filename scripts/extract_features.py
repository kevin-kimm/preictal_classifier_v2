"""Extract D1 features for every labeled window.

For each recording: harmonize (in one-hour pieces), cut 30 s windows every 5 s,
compute the 15 features per derivation (src/preictal/features/build_features.py),
and save them with the window labels and times.

Usage, from the repo root with .venv active:
    python scripts/extract_features.py                              CHB-MIT and Siena (D1)
    python scripts/extract_features.py --datasets tusz mental_arith  false-alarm test sets

Output (not in Git):
    data/processed/features/<dataset>/<recording>.npz
    data/processed/features/timelines.json   seizure onsets per timeline, for alarm scoring

Resumable: recordings already done with the same feature version are skipped,
so an interrupted run can simply be started again.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.config import load_config  # noqa: E402
from preictal.data.edf import read_header  # noqa: E402
from preictal.data.labels import INTERICTAL, LabelRules, build_timelines, window_labels  # noqa: E402
from preictal.data.loaders import DEFAULT_CORRECTIONS, discover  # noqa: E402
from preictal.features.build_features import feature_version, recording_features  # noqa: E402
from preictal.models.train import feature_file  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


def work(job):
    path, out, meta, starts, labels, t_end, length_s = job
    hdr = read_header(path)
    feats, present = recording_features(hdr, starts, length_s)
    tmp = out.with_name(out.stem + ".tmp.npz")
    np.savez(tmp, features=feats, present=present, labels=labels, starts=starts, t_end=t_end,
             **{k: np.array(v) for k, v in meta.items()})
    tmp.rename(out)
    return out.name, len(starts), float(hdr.duration_s)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datasets", nargs="+", default=["chbmit", "siena"])
    ap.add_argument("--data-root", type=Path, default=REPO / "data" / "raw")
    ap.add_argument("--out", type=Path, default=REPO / "data" / "processed" / "features")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    length_s, step_s = cfg["windows"]["length_s"], cfg["windows"]["step_s"]
    corrections = DEFAULT_CORRECTIONS.read_text() if DEFAULT_CORRECTIONS.exists() else ""
    version = feature_version(cfg, corrections)

    recs = discover(args.data_root, datasets=tuple(args.datasets))
    print(f"{len(recs)} recordings in {', '.join(args.datasets)}; building timelines...")
    timelines = build_timelines(recs, rules)

    tl_file = args.out / "timelines.json"
    tl_info = json.loads(tl_file.read_text()) if tl_file.exists() else {}
    fa_only = set(cfg["training"]["false_alarm_sets"])
    jobs, skipped, too_short, no_interictal, hours = [], 0, 0, 0, 0.0
    for tl in timelines:
        key = "|".join(map(str, tl.key))
        tl_info[key] = {"subject": tl.subject, "dataset": tl.dataset, "role": tl.role,
                        "onsets": [on for on, _ in tl.seizures],
                        "eligible_onsets": [e.onset for e in tl.events if e.eligible]}
        for p in tl.placed:
            starts, labels = window_labels(p, tl, rules, length_s, step_s)
            if len(starts) == 0:
                too_short += 1
                continue
            if tl.dataset in fa_only and not (labels == INTERICTAL).any():
                no_interictal += 1   # false-alarm sets only use interictal windows
                continue
            out = feature_file(args.out, tl.dataset, p.rec.rel_path)
            if out.exists():
                try:
                    z = np.load(out)
                    if str(z["version"]) == version and len(z["labels"]) == len(starts):
                        skipped += 1
                        continue
                except (OSError, ValueError, KeyError):
                    pass
            out.parent.mkdir(parents=True, exist_ok=True)
            meta = {"version": version, "dataset": tl.dataset, "subject": tl.subject, "timeline": key,
                    "role": tl.role, "recording": p.rec.rel_path}
            jobs.append((str(p.rec.path), out, meta, starts, labels.astype(np.int8),
                         p.start + starts + length_s, length_s))
            hours += p.duration / 3600
    args.out.mkdir(parents=True, exist_ok=True)
    tl_file.write_text(json.dumps(tl_info))

    print(f"{len(jobs)} recordings to process ({hours:.0f} h of EEG), {skipped} already done, "
          f"{too_short} shorter than one window"
          + (f", {no_interictal} with no interictal time (false-alarm sets only need interictal)" if no_interictal else "")
          + f". Feature version {version}.")
    t0, done_windows = time.time(), 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(work, j) for j in jobs]
        bar = tqdm(total=round(hours, 1), unit="h EEG") if tqdm else None
        for fut in as_completed(futures):
            name, n, dur = fut.result()
            done_windows += n
            if bar:
                bar.update(round(dur / 3600, 3))
        if bar:
            bar.close()
    print(f"Done: {len(jobs)} recordings, {done_windows:,} windows in {(time.time() - t0) / 60:.1f} min.")
    print(f"Features in {args.out}")


if __name__ == "__main__":
    main()

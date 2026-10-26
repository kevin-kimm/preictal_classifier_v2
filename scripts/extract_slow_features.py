"""Infra-slow features for every window that already has frozen features
(docs/evaluation_methods.md v1.25, Section 14.7; src/preictal/features/slow.py).

Reads the window start times from the existing feature files, so the new features line up with them
exactly, and writes one file per recording next to them:

    data/processed/features_v2_slow/<dataset>/<recording>.npz         CHB-MIT and Siena
    data/processed/features_seizeit2_slow/seizeit2/<recording>.npz    SeizeIT2 development patients

Usage, from the repo root with .venv active:
    python scripts/extract_slow_features.py                        CHB-MIT and Siena
    python scripts/extract_slow_features.py --dataset seizeit2     SeizeIT2 development patients (never the lockbox)

Resumable: files already made with the same version are skipped.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.config import load_config  # noqa: E402
from preictal.features.slow import LEAD_S, SLOW_VERSION, pool_slow, slow_features  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

CHUNK_WINDOWS = 720            # one hour of windows at a time
SZ2_ROOT = REPO / "data" / "raw" / "seizeit2_v1.1.0"


def read_stretch(dataset: str, path: Path, a: float, b: float):
    """Signals (channels x samples at 256 Hz) from a to b seconds into the recording, and their start time."""
    if dataset == "seizeit2":
        from preictal.data.edf import read_header
        from preictal.data.harmonize import TARGET_FS, resample
        from preictal.data.seizeit2 import CHANNELS, read_bte
        hdr = read_header(path)
        rs = hdr.record_s
        r0, r1 = int(math.floor(a / rs)), min(hdr.n_records, int(math.ceil(b / rs)))
        raw, present, fs_in, _ = read_bte(path, r0, r1 - r0)
        x = np.full((len(CHANNELS), int(round((r1 - r0) * rs * TARGET_FS)) + 2), np.nan)
        n = None
        for j in range(len(CHANNELS)):
            if present[j]:
                yv = resample(raw[j], fs_in, TARGET_FS)
                n = len(yv) if n is None else min(n, len(yv))
                x[j, :len(yv)] = yv
        x = x[:, :n] if n else x[:, :0]
        return x, TARGET_FS, r0 * rs
    from preictal.data.edf import read_header
    from preictal.data.harmonize import harmonize
    hdr = read_header(path)
    h = harmonize(hdr, start_s=a, stop_s=min(b, hdr.duration_s))
    return h.data, h.fs, h.t0


def work(job):
    dataset, raw_path, feat_file, out_file, length_s = job
    z = np.load(feat_file)
    starts = z["starts"].astype(float)
    ends = starts + length_s
    per = None
    for k0 in range(0, len(starts), CHUNK_WINDOWS):
        e = ends[k0:k0 + CHUNK_WINDOWS]
        a = max(0.0, e[0] - LEAD_S)
        x, fs, t0 = read_stretch(dataset, Path(raw_path), a, e[-1])
        f = slow_features(x, fs, t0, e)
        if per is None:
            per = np.full((len(starts), f.shape[1], f.shape[2]), np.nan, dtype=np.float32)
        per[k0:k0 + len(e)] = f
    if per is None:
        per = np.zeros((0, 1, 3), dtype=np.float32)
    tmp = out_file.with_name(out_file.stem + ".tmp.npz")
    np.savez(tmp, starts=starts, per_channel=per, pooled=pool_slow(per), version=np.array(SLOW_VERSION),
             recording=z["recording"])
    tmp.rename(out_file)
    return out_file.name, len(starts)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", choices=["chbmit_siena", "seizeit2"], default="chbmit_siena")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    sz2 = args.dataset == "seizeit2"
    length_s = float(load_config()["windows"]["length_s"])
    feat_dir = REPO / "data" / "processed" / ("features_seizeit2" if sz2 else "features_v2")
    out_dir = feat_dir.parent / (feat_dir.name + "_slow")
    datasets = ("seizeit2",) if sz2 else ("chbmit", "siena")
    allowed = None
    if sz2:
        import yaml
        split = yaml.safe_load((REPO / "configs" / "seizeit2_split.yaml").read_text())
        allowed = {f"seizeit2:{s}" for s in split["development"]}
    jobs = []
    for ds in datasets:
        for f in sorted((feat_dir / ds).glob("*.npz")):
            z = np.load(f)
            if allowed is not None and str(z["subject"]) not in allowed:
                continue                                  # never touch lockbox recordings
            rel = str(z["recording"])
            raw = (SZ2_ROOT.parent / rel) if sz2 else (REPO / "data" / "raw" / rel)
            out = out_dir / ds / f.name
            if out.exists():
                try:
                    if str(np.load(out)["version"]) == SLOW_VERSION:
                        continue
                except (OSError, ValueError, KeyError):
                    pass
            out.parent.mkdir(parents=True, exist_ok=True)
            jobs.append((ds, str(raw), str(f), out, length_s))
    print(f"{len(jobs)} recordings to process ({args.dataset}); output in {out_dir}")
    t0 = time.time()
    n_win = 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(work, j) for j in jobs]
        it = tqdm(as_completed(futures), total=len(futures), unit="file") if tqdm else as_completed(futures)
        for fut in it:
            _, n = fut.result()
            n_win += n
    print(f"Done: {len(jobs)} recordings, {n_win:,} windows in {(time.time() - t0) / 60:.1f} min.")


if __name__ == "__main__":
    main()

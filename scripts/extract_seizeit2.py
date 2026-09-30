"""Extract SeizeIT2 features and labels with the frozen rules (docs/evaluation_methods.md v1.15).

Development patients (default): features, labels and a feasibility report, used to build and
check the adapter. Lockbox patients: only for the single lockbox run after the freeze, and
only with --lockbox-run; the script refuses otherwise.

Usage, from the repo root with .venv active:
    python scripts/extract_seizeit2.py                                  the 25 development patients
    python scripts/extract_seizeit2.py --group lockbox --lockbox-run    the lockbox run only

Outputs:
    data/processed/features_seizeit2/seizeit2/<file>.npz and timelines.json (not in Git)
    results/seizeit2_dev/feasibility.md (development patients only)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.config import load_config  # noqa: E402
from preictal.data.labels import ICTAL, INTERICTAL, PREICTAL, LabelRules  # noqa: E402
from preictal.data.seizeit2 import (  # noqa: E402
    FEATURE_CODE, VERSION_TEXT, discover_patient, recording_features, timeline, window_labels,
)
from preictal.features.build_features import feature_version  # noqa: E402
from preictal.models.train import feature_file  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

ROOT = REPO / "data" / "raw" / "seizeit2_v1.1.0"


def work(job):
    path, out, meta, starts, labels, t_end, length_s = job
    feats, conn, present = recording_features(Path(path), starts, length_s)
    tmp = out.with_name(out.stem + ".tmp.npz")
    np.savez(tmp, features=feats, connectivity=conn, present=present, labels=labels, starts=starts, t_end=t_end,
             **{k: np.array(v) for k, v in meta.items()})
    tmp.rename(out)
    return out.name


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--group", choices=["development", "lockbox"], default="development")
    ap.add_argument("--lockbox-run", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", type=Path, default=REPO / "data" / "processed" / "features_seizeit2")
    args = ap.parse_args()

    if args.group == "lockbox":
        tags = subprocess.run(["git", "tag", "-l", "freeze-v1.13"], cwd=REPO, capture_output=True, text=True).stdout
        if not args.lockbox_run or "freeze-v1.13" not in tags:
            sys.exit("Refusing to touch the lockbox: it is opened only for the single lockbox run, after the freeze "
                     "(needs --lockbox-run and the freeze-v1.13 Git tag).")

    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    length_s, step_s = cfg["windows"]["length_s"], cfg["windows"]["step_s"]
    version = feature_version(cfg, VERSION_TEXT, FEATURE_CODE)
    split = yaml.safe_load((REPO / "configs" / "seizeit2_split.yaml").read_text())
    subjects = split[args.group]
    print(f"{len(subjects)} {args.group} patients; feature version {version}")

    tl_file = args.out / "timelines.json"
    tl_info = json.loads(tl_file.read_text()) if tl_file.exists() else {}
    jobs, summary = [], []
    for sub in subjects:
        patient = discover_patient(ROOT, sub)
        tl = timeline(patient, rules)
        key = "|".join(tl.key)
        tl_info[key] = {"subject": tl.subject, "dataset": "seizeit2", "role": "train_test",
                        "onsets": [on for on, _ in tl.seizures],
                        "eligible_onsets": [e.onset for e in tl.events if e.eligible]}
        hours = {PREICTAL: 0.0, ICTAL: 0.0, INTERICTAL: 0.0}
        for p in tl.placed:
            starts, labels = window_labels(p, tl, rules, length_s, step_s)
            for c in hours:
                hours[c] += (labels == c).sum() * step_s / 3600
            if len(starts) == 0:
                continue
            out = feature_file(args.out, "seizeit2", p.rec.rel_path)
            if out.exists():
                try:
                    z = np.load(out)
                    if str(z["version"]) == version and len(z["labels"]) == len(starts):
                        continue
                except (OSError, ValueError, KeyError):
                    pass
            out.parent.mkdir(parents=True, exist_ok=True)
            meta = {"version": version, "dataset": "seizeit2", "subject": tl.subject, "timeline": key,
                    "role": "train_test", "recording": p.rec.rel_path}
            jobs.append((str(p.rec.path), out, meta, starts, labels.astype(np.int8), p.start + starts + length_s,
                         length_s))
        n_elig = sum(e.eligible for e in tl.events)
        summary.append({"subject": tl.subject, "files": len(tl.placed), "eeg_h": sum(patient.durations) / 3600,
                        "seizures": len(tl.seizures), "events": len(tl.events), "eligible": n_elig,
                        "preictal_h": hours[PREICTAL], "interictal_h": hours[INTERICTAL],
                        "qualifies": n_elig >= 2 and hours[INTERICTAL] >= 1.0})
    args.out.mkdir(parents=True, exist_ok=True)
    tl_file.write_text(json.dumps(tl_info))

    print(f"{len(jobs)} files to process")
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(work, j) for j in jobs]
        it = tqdm(as_completed(futures), total=len(futures), unit="file") if tqdm else as_completed(futures)
        for f in it:
            f.result()

    q = sum(s["qualifies"] for s in summary)
    tot = {k: sum(s[k] for s in summary) for k in ("files", "eeg_h", "seizures", "events", "eligible",
                                                    "preictal_h", "interictal_h")}
    print(f"Seizures {tot['seizures']}, events {tot['events']}, eligible {tot['eligible']} "
          f"(preictal period inside the seizure's own file); preictal {tot['preictal_h']:.1f} h, "
          f"interictal {tot['interictal_h']:.1f} h; patients qualifying for the personalized test: {q} of {len(summary)}")
    if args.group == "development":
        out = REPO / "results" / "seizeit2_dev"
        out.mkdir(parents=True, exist_ok=True)
        lines = ["# SeizeIT2 development patients: feasibility with the frozen rules", "",
                 f"Feature version {version}. Labels follow docs/evaluation_methods.md v1.13 Section 11.5: files back "
                 "to back in run order, preictal windows only inside the seizure's own file.", "",
                 f"Totals: {tot['files']} files, {tot['eeg_h']:.0f} h of EEG, {tot['seizures']} seizures in "
                 f"{tot['events']} events, {tot['eligible']} eligible; {tot['preictal_h']:.1f} h preictal, "
                 f"{tot['interictal_h']:.1f} h interictal; {q} of {len(summary)} patients qualify "
                 "(at least 2 eligible seizures and 1 h of interictal EEG).", "",
                 "| Patient | Files | EEG h | Seizures | Events | Eligible | Preictal h | Interictal h | Qualifies |",
                 "|---|---|---|---|---|---|---|---|---|"]
        for s in summary:
            lines.append(f"| {s['subject']} | {s['files']} | {s['eeg_h']:.1f} | {s['seizures']} | {s['events']} "
                         f"| {s['eligible']} | {s['preictal_h']:.1f} | {s['interictal_h']:.1f} | "
                         f"{'yes' if s['qualifies'] else 'no'} |")
        (out / "feasibility.md").write_text("\n".join(lines) + "\n")
        print(f"Report: {out / 'feasibility.md'}")


if __name__ == "__main__":
    main()

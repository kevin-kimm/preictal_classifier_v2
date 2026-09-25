"""VT-02, VT-03 and VT-05 on the real data.

Runs the unit tests for VT-02 to VT-04, then checks the harmonization code on
every recording under data/raw/:

    VT-02  every channel label is mapped or excluded with a reason
    VT-03  median absolute amplitude of each harmonized derivation (slow: reads all data)
    VT-05  every seizure annotation lands inside its harmonized recording, counts
           match the VT-01 audit, and 10 random seizures are plotted for review

Usage, from the repo root with .venv active:
    python scripts/check_harmonization.py                    all checks
    python scripts/check_harmonization.py --skip-amplitude   skip the slow VT-03 corpus check

Outputs in results/d1/:
    harmonization_check.md         summary with pass/fail
    channel_log.csv                every distinct channel label per dataset and how it was handled
    derivation_availability.csv    which of the 18 derivations each recording has
    amplitude_check.csv            derivations with median |amplitude| outside 1-200 uV
    annotation_check.csv           every seizure with its sample position at 256 Hz
    figures/seizure_XX.png         seizures chosen for visual review
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import random
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.data.edf import read_header  # noqa: E402
from preictal.data.harmonize import (  # noqa: E402
    DERIVATIONS, TARGET_FS, expected_length, harmonize, looks_like_eeg, plan_montage,
)
from preictal.data.loaders import discover  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

SEIZURE_DATASETS = ("chbmit", "siena", "tusz")
AMP_LOW, AMP_HIGH = 1.0, 200.0


def git_commit() -> str:
    try:
        c = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                           capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "src", "scripts"], cwd=REPO,
                               capture_output=True, text=True, check=True).stdout.strip()
        return c + (" (uncommitted code changes)" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def progress(iterable, total, desc):
    return tqdm(iterable, total=total, desc=desc) if tqdm else iterable


# ---------------------------------------------------------------- unit tests

def run_unit_tests() -> tuple[bool, str]:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/test_harmonize.py",
                        "tests/test_loaders.py"], cwd=REPO, capture_output=True, text=True)
    lines = [x for x in r.stdout.strip().splitlines() if x.strip()]
    return r.returncode == 0, (lines[-1] if lines else r.stderr.strip()[-200:])


# ---------------------------------------------------------------- VT-02

def check_channels(recs, out_dir):
    labels = Counter()
    availability = []
    for rec in progress(recs, len(recs), "VT-02 channel mapping"):
        hdr = read_header(rec.path)
        plan = plan_montage(hdr.labels)
        seen = set()
        for e in plan.channel_log:
            key = (rec.dataset, e["raw_label"], e["kind"], e["canonical"], e["status"])
            if key not in seen:
                seen.add(key)
                labels[key] += 1
        missing = [d for d, p in zip(DERIVATIONS, plan.present) if not p]
        availability.append({"dataset": rec.dataset, "recording": rec.rel_path,
                             "n_present": int(plan.present.sum()), "missing": ";".join(missing)})

    with open(out_dir / "channel_log.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["dataset", "raw_label", "kind", "canonical", "status", "n_recordings"])
        for key, n in sorted(labels.items()):
            w.writerow([*key, n])
    with open(out_dir / "derivation_availability.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["dataset", "recording", "n_present", "missing"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(availability)

    unmapped = sorted({(k[0], k[1]) for k in labels if k[4] == "unrecognized label" and looks_like_eeg(k[1])})
    other_unrecognized = sorted({(k[0], k[1]) for k in labels
                                 if k[4] == "unrecognized label" and not looks_like_eeg(k[1])})
    per_ds = defaultdict(Counter)
    for row in availability:
        per_ds[row["dataset"]][row["n_present"]] += 1
    return {"unmapped": unmapped, "other_unrecognized": other_unrecognized,
            "availability": {ds: dict(sorted(c.items(), reverse=True)) for ds, c in per_ds.items()},
            "status_counts": Counter(k[4] for k in labels)}


# ---------------------------------------------------------------- VT-05

def harmonized_length(hdr) -> int:
    plan = plan_montage(hdr.labels)
    idx = plan.used_indices
    if not idx:
        return int(round(hdr.duration_s * TARGET_FS))
    return min(expected_length(int(hdr.samples_per_record[i] * hdr.n_records), hdr.fs(i))
               for i in idx)


def check_annotations(recs, out_dir):
    rows, problems = [], []
    counts = Counter()
    for rec in progress([r for r in recs if r.dataset in SEIZURE_DATASETS], None, "VT-05 annotations"):
        if not rec.seizures:
            continue
        n = harmonized_length(read_header(rec.path))
        for k, (on, off) in enumerate(rec.seizures, 1):
            counts[rec.dataset] += 1
            i_on, i_off = int(round(on * TARGET_FS)), int(round(off * TARGET_FS))
            err = max(abs(i_on / TARGET_FS - on), abs(i_off / TARGET_FS - off)) * TARGET_FS
            ok = 0 <= i_on < i_off <= n and err <= 1
            rows.append({"dataset": rec.dataset, "recording": rec.rel_path, "seizure": k,
                         "onset_s": on, "offset_s": off, "onset_sample": i_on,
                         "offset_sample": i_off, "n_samples": n,
                         "max_error_samples": round(err, 3), "ok": ok})
            if not ok:
                problems.append(f"{rec.rel_path} seizure {k}: onset {on} s, offset {off} s, "
                                f"recording {n / TARGET_FS:.1f} s")
    with open(out_dir / "annotation_check.csv", "w", newline="") as f:
        fields = ["dataset", "recording", "seizure", "onset_s", "offset_s", "onset_sample",
                  "offset_sample", "n_samples", "max_error_samples", "ok"]
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    audit, mismatches = {}, []
    audit_file = out_dir / "data_audit_summary.json"
    if audit_file.exists():
        audit = json.loads(audit_file.read_text())["datasets"]
        for ds in SEIZURE_DATASETS:
            expected = audit.get(ds, {}).get("seizures")
            if expected is not None and expected != counts[ds]:
                mismatches.append(f"{ds}: loader found {counts[ds]} seizures, VT-01 audit found {expected}")
    else:
        mismatches.append("results/d1/data_audit_summary.json not found; run the VT-01 audit first")
    durations = [r["offset_s"] - r["onset_s"] for r in rows]
    return {"rows": rows, "problems": problems, "counts": dict(counts), "mismatches": mismatches,
            "duration_range": (min(durations), max(durations)) if durations else None}


def plot_seizures(recs, out_dir, n_total=10, per_dataset=3, seed=0):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rng = random.Random(seed)
    pool = {ds: [(r, k) for r in recs if r.dataset == ds for k in range(len(r.seizures))]
            for ds in SEIZURE_DATASETS}
    chosen = []
    for ds in SEIZURE_DATASETS:
        chosen += rng.sample(pool[ds], min(per_dataset, len(pool[ds])))
    rest = [x for ds in SEIZURE_DATASETS for x in pool[ds] if x not in chosen]
    chosen += rng.sample(rest, max(0, min(n_total - len(chosen), len(rest))))

    from scipy.signal import butter, sosfiltfilt
    sos = butter(4, [0.5, 40], btype="band", fs=TARGET_FS, output="sos")  # display only

    fig_dir = out_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for i, (rec, k) in enumerate(chosen, 1):
        h = harmonize(read_header(rec.path))
        on, off = rec.seizures[k]
        a = max(0, int((on - 20) * h.fs))           # 20 s before onset
        b = min(h.n_samples, int((on + 40) * h.fs))  # 40 s after onset
        t = np.arange(a, b) / h.fs
        shown = {j: sosfiltfilt(sos, h.data[j, a:b]) for j in range(len(h.derivations))
                 if h.present[j] and b - a > 100}
        scale = np.median([np.median(np.abs(x)) for x in shown.values()]) if shown else 1.0
        spacing = max(20.0, 8 * scale)
        fig, ax = plt.subplots(figsize=(12, 8))
        for j, name in enumerate(h.derivations):
            y = -j * spacing
            if j in shown:
                ax.plot(t, np.clip(shown[j], -2 * spacing, 2 * spacing) + y, lw=0.5, color="black")
            ax.text(t[0] - 0.3, y, name, ha="right", va="center", fontsize=7,
                    color="black" if h.present[j] else "lightgrey")
        ax.axvline(on, color="red", lw=1.2, label="annotated onset")
        if off <= t[-1]:
            ax.axvline(off, color="blue", lw=1.2, label="annotated offset")
        ax.set_yticks([])
        ax.set_xlim(t[0], t[-1])
        ax.set_xlabel("time from recording start (s)")
        ax.set_title(f"{rec.dataset}: {Path(rec.rel_path).name}, seizure {k + 1} "
                     f"(onset {on:.1f} s, offset {off:.1f} s) | display filter 0.5-40 Hz, "
                     f"spacing {spacing:.0f} uV", fontsize=10)
        ax.legend(loc="upper right", fontsize=8)
        fig.tight_layout()
        name = f"seizure_{i:02d}_{rec.dataset}.png"
        fig.savefig(fig_dir / name, dpi=110)
        plt.close(fig)
        written.append((name, rec.rel_path, k + 1))
    return written


# ---------------------------------------------------------------- VT-03

def amplitude_worker(args):
    dataset, rel, path = args
    hdr = read_header(path)
    h = harmonize(hdr)
    meds = []
    for j, name in enumerate(h.derivations):
        if h.present[j]:
            meds.append((name, float(np.median(np.abs(h.data[j])))))
    length_ok = abs(h.n_samples - hdr.duration_s * TARGET_FS) <= 1
    return dataset, rel, meds, length_ok, h.warnings


def check_amplitude(recs, out_dir, workers):
    per_ds = defaultdict(list)
    outside, length_bad, warnings = [], [], Counter()
    jobs = [(r.dataset, r.rel_path, str(r.path)) for r in recs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(amplitude_worker, j) for j in jobs]
        for fut in progress(as_completed(futures), len(futures), "VT-03 amplitude"):
            ds, rel, meds, length_ok, warn = fut.result()
            for name, m in meds:
                per_ds[ds].append(m)
                if not AMP_LOW <= m <= AMP_HIGH:
                    outside.append((ds, rel, name, m))
            if not length_ok:
                length_bad.append(rel)
            for w in warn:
                warnings[w.split(":")[-1].strip()] += 1
    with open(out_dir / "amplitude_check.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["dataset", "recording", "derivation", "median_abs_uV"])
        for row in sorted(outside):
            w.writerow([*row[:3], round(row[3], 3)])
    total = sum(len(v) for v in per_ds.values())
    within = total - len(outside)
    stats = {ds: {"channels": len(v),
                  "within": sum(AMP_LOW <= m <= AMP_HIGH for m in v),
                  "p5": float(np.percentile(v, 5)), "median": float(np.median(v)),
                  "p95": float(np.percentile(v, 95))} for ds, v in per_ds.items() if v}
    return {"total": total, "within": within, "fraction": within / total if total else 0.0,
            "stats": stats, "length_bad": length_bad, "warnings": warnings}


# ---------------------------------------------------------------- report

def write_report(out_dir, unit, ch, ann, figs, amp, n_recs, notes):
    ok_unit, unit_line = unit
    vt02 = ok_unit and not ch["unmapped"]
    vt05 = ok_unit and not ann["problems"] and not ann["mismatches"]
    lines = [
        "# Harmonization checks (VT-02 to VT-05)",
        "",
        f"Generated {datetime.now().isoformat(timespec='seconds')} · commit {git_commit()} "
        f"· Python {platform.python_version()} · {n_recs} recordings",
        "",
        "## Results",
        "",
        "| Test | Part | Result |",
        "|---|---|---|",
        f"| VT-02 to VT-04 | Unit tests (`tests/test_harmonize.py`, `tests/test_loaders.py`) "
        f"| {'PASS' if ok_unit else 'FAIL'}: {unit_line} |",
        f"| VT-02 | Every channel mapped or logged; zero unmapped EEG channels "
        f"| {'PASS' if vt02 else 'FAIL'}: {len(ch['unmapped'])} unmapped EEG labels |",
    ]
    if amp is None:
        lines.append("| VT-03 | Corpus amplitude check | NOT RUN (--skip-amplitude) |")
    else:
        vt03 = ok_unit and amp["fraction"] >= 0.95 and not amp["length_bad"]
        lines.append(f"| VT-03 | ≥ 95% of derivations with median amplitude in 1–200 µV; lengths "
                     f"= duration × 256 ± 1 | {'PASS' if vt03 else 'FAIL'}: "
                     f"{amp['within']}/{amp['total']} ({100 * amp['fraction']:.1f}%) in range, "
                     f"{len(amp['length_bad'])} length mismatches |")
    lines += [
        "| VT-04 | Montage conversion | See unit tests |",
        f"| VT-05 | Every seizure inside its recording, within ±1 sample; counts match VT-01 "
        f"| {'PASS' if vt05 else 'FAIL'}: {len(ann['rows'])} seizures checked, "
        f"{len(ann['problems'])} problems, {len(ann['mismatches'])} count mismatches |",
        f"| VT-05 | Visual review of {len(figs)} plotted seizures | PENDING: review the figures below |",
        "",
        "## VT-02 channel mapping",
        "",
        "Channel labels by how they were handled (distinct labels per dataset):",
        "",
    ]
    lines += [f"- {status}: {n}" for status, n in sorted(ch["status_counts"].items())]
    lines += ["", "Recordings by number of derivations present (out of 18):", "",
              "| Dataset | Derivations present: recordings |", "|---|---|"]
    lines += [f"| {ds} | " + ", ".join(f"{k}: {v}" for k, v in c.items()) + " |"
              for ds, c in sorted(ch["availability"].items())]
    if ch["unmapped"]:
        lines += ["", "Unmapped EEG labels:", ""] + [f"- {ds}: `{lab}`" for ds, lab in ch["unmapped"]]
    if ch["other_unrecognized"]:
        lines += ["", "Unrecognized labels without an EEG prefix (logged, not used):", "",
                  ", ".join(f"{ds}: `{lab}`" for ds, lab in ch["other_unrecognized"])]
    if amp is not None:
        lines += ["", "## VT-03 amplitude", "",
                  "Median absolute amplitude per derivation (µV):", "",
                  "| Dataset | Derivations | In 1–200 µV | 5th pct | Median | 95th pct |",
                  "|---|---|---|---|---|---|"]
        lines += [f"| {ds} | {s['channels']} | {100 * s['within'] / s['channels']:.1f}% "
                  f"| {s['p5']:.1f} | {s['median']:.1f} | {s['p95']:.1f} |"
                  for ds, s in sorted(amp["stats"].items())]
        lines += ["", "Out-of-range derivations are listed in `amplitude_check.csv`."]
        if amp["warnings"]:
            lines += ["", "Harmonization warnings:", ""]
            lines += [f"- {w} ({n} channels)" for w, n in amp["warnings"].most_common()]
    lines += ["", "## VT-05 annotations", "",
              "Seizures checked per dataset: " + ", ".join(f"{k} {v}" for k, v in sorted(ann["counts"].items()))]
    if ann["duration_range"]:
        lo, hi = ann["duration_range"]
        lines.append(f"Seizure durations range from {lo:.1f} s to {hi:.1f} s.")
    for label, items in (("Problems", ann["problems"]), ("Count mismatches", ann["mismatches"])):
        if items:
            lines += ["", f"{label}:", ""] + [f"- {x}" for x in items[:50]]
    lines += ["", "Seizures for visual review (red = annotated onset, blue = offset). Check that "
              "each onset marker lines up with a visible change in the EEG:", "",
              "| Figure | Recording | Seizure |", "|---|---|---|"]
    lines += [f"| [{f}](figures/{f}) | {rec} | {k} |" for f, rec, k in figs]
    if notes:
        lines += ["", "## Loader notes", ""] + [f"- {x}" for x in notes]
    (out_dir / "harmonization_check.md").write_text("\n".join(lines) + "\n")
    return vt02, vt05


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", type=Path, default=REPO / "data" / "raw")
    ap.add_argument("--out", type=Path, default=REPO / "results" / "d1")
    ap.add_argument("--skip-amplitude", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    print("Running unit tests...")
    unit = run_unit_tests()
    print(f"  {'PASS' if unit[0] else 'FAIL'}: {unit[1]}")

    notes = []
    recs = discover(args.data_root, notes=notes)
    print(f"{len(recs)} recordings found")

    ch = check_channels(recs, args.out)
    ann = check_annotations(recs, args.out)
    print("Plotting seizures for visual review...")
    figs = plot_seizures(recs, args.out)
    amp = None if args.skip_amplitude else check_amplitude(recs, args.out, args.workers)

    vt02, vt05 = write_report(args.out, unit, ch, ann, figs, amp, len(recs), notes)
    print()
    print(f"VT-02 channel mapping:  {'PASS' if vt02 else 'FAIL'} ({len(ch['unmapped'])} unmapped EEG labels)")
    if amp is None:
        print("VT-03 amplitude:        not run")
    else:
        print(f"VT-03 amplitude:        {100 * amp['fraction']:.1f}% of derivations in range, "
              f"{len(amp['length_bad'])} length mismatches")
    print(f"VT-05 annotations:      {'PASS' if vt05 else 'FAIL'} ({len(ann['rows'])} seizures, "
          f"{len(ann['problems'])} problems, {len(ann['mismatches'])} count mismatches)")
    print(f"Report: {args.out / 'harmonization_check.md'}")


if __name__ == "__main__":
    main()

"""VT-01: data inventory and integrity check for data/raw/.

For every file under data/raw/ this records the size and SHA-256 checksum,
opens every EDF header, and counts patients, recordings, hours and seizures
per dataset. If a previous full run exists, the new results are compared
with it (VT-01 requires two identical runs).

Usage, from the repo root with .venv active:
    python scripts/audit_data.py            full run, valid VT-01 evidence
    python scripts/audit_data.py --quick    skips checksums; for a quick look only

Outputs in results/d1/ (a --quick run writes to results/d1/quick/ instead):
    data_manifest.csv         one row per file
    data_audit.md             summary report with the VT-01 checklist
    data_audit_summary.json   counts and fingerprints, used to compare runs
    channel_labels.csv        EDF channel labels per dataset (input for VT-02)
    tuar_tusz_overlap.csv     patient IDs that appear in both TUAR and TUSZ
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from statistics import mode

try:
    from tqdm import tqdm
except ImportError:  # progress bar is optional
    tqdm = None

REPO = Path(__file__).resolve().parents[1]

# Dataset key -> folder-name prefix under data/raw/
DATASETS = {
    "chbmit": "chbmit_",
    "siena": "siena_",
    "tusz": "tusz_",
    "tuar": "tuar_",
    "mental_arith": "mental_arith_",
}

MANIFEST_COLUMNS = [
    "dataset", "folder", "path", "size_bytes", "sha256",
    "is_edf", "edf_ok", "error", "warning",
    "patient", "session", "split", "montage",
    "n_signals", "fs_hz", "duration_s", "n_seizures",
]

TUH_NAME = re.compile(r"^([a-z]{8})_(s\d{3})_(t\d{3})")
EDF_ANNOTATIONS = "EDF Annotations"


# ---------------------------------------------------------------- file scan

def find_files(data_root: Path):
    """Return (dataset_key, folder_name, path) for every non-hidden file."""
    items, hidden = [], 0
    for folder in sorted(p for p in data_root.iterdir() if p.is_dir()):
        key = next((k for k, pre in DATASETS.items() if folder.name.startswith(pre)), "other")
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(data_root)
            if any(part.startswith(".") for part in rel.parts):
                hidden += 1  # .DS_Store, rsync temp files
                continue
            items.append((key, folder.name, path))
    return items, hidden


def parse_ids(key: str, rel: Path) -> dict:
    """Patient/session/split/montage from a path relative to its dataset folder."""
    ids = {"patient": "", "session": "", "split": "", "montage": ""}
    name = rel.name
    if key == "chbmit":
        m = re.match(r"(chb\d+)", name, re.I)
        if m:
            ids["patient"] = m.group(1).lower()
    elif key == "siena":
        m = re.match(r"(PN\d+)", name, re.I)
        if m:
            ids["patient"] = m.group(1).upper()
    elif key == "mental_arith":
        m = re.match(r"(Subject\d+)", name, re.I)
        if m:
            ids["patient"] = m.group(1)
    elif key in ("tusz", "tuar"):
        m = TUH_NAME.match(name)
        if m:
            ids["patient"], ids["session"] = m.group(1), m.group(2)
            ids["montage"] = rel.parent.name
            ids["split"] = next((p for p in rel.parts if p in ("train", "dev", "eval")), "")
    return ids


# ---------------------------------------------------------------- EDF header

def read_edf_header(path: Path, size: int) -> dict:
    """Read an EDF header without loading signal data. Raises ValueError on problems."""
    with open(path, "rb") as f:
        fixed = f.read(256)
        if len(fixed) < 256:
            raise ValueError("file is shorter than the 256-byte EDF header")

        def field(a, b, cast):
            text = fixed[a:b].decode("ascii", "replace").strip()
            try:
                return cast(text)
            except ValueError:
                raise ValueError(f"unreadable header field at bytes {a}-{b}: {text!r}") from None

        header_bytes = field(184, 192, int)
        n_records = field(236, 244, int)
        record_s = field(244, 252, float)
        ns = field(252, 256, int)
        if ns <= 0:
            raise ValueError(f"invalid number of signals: {ns}")
        sig = f.read(ns * 256)
        if len(sig) < ns * 256:
            raise ValueError("signal header is truncated")

    def block(offset_per_signal, width):
        base = ns * offset_per_signal
        return [sig[base + i * width: base + (i + 1) * width].decode("latin-1").strip()
                for i in range(ns)]

    labels = block(0, 16)
    try:
        spr = [int(x) for x in block(216, 8)]  # samples per data record
    except ValueError:
        raise ValueError("unreadable samples-per-record field") from None
    if header_bytes != 256 * (ns + 1):
        raise ValueError(f"header size {header_bytes} does not match {ns} signals")

    warnings = []
    record_bytes = 2 * sum(spr)
    if n_records < 0:
        n_records = (size - header_bytes) // record_bytes if record_bytes else 0
        warnings.append("record count missing from header, inferred from file size")
    expected = header_bytes + n_records * record_bytes
    if size < expected:
        raise ValueError(f"truncated: header implies {expected} bytes, file has {size}")
    if size > expected:
        warnings.append(f"{size - expected} extra bytes after last record")

    eeg = [(label, s) for label, s in zip(labels, spr) if label != EDF_ANNOTATIONS]
    fs = [round(s / record_s, 3) for _, s in eeg] if record_s > 0 else []
    fs_mode = mode(fs) if fs else ""
    if fs_mode != "" and float(fs_mode).is_integer():
        fs_mode = int(fs_mode)
    return {
        "n_signals": len(eeg),
        "fs_hz": fs_mode,
        "duration_s": round(n_records * record_s, 3),
        "labels": [label for label, _ in eeg],
        "warning": "; ".join(warnings),
    }


def process_file(item, data_root: Path, do_hash: bool) -> dict:
    key, folder, path = item
    size = path.stat().st_size
    rel_in_dataset = path.relative_to(data_root / folder)
    row = {c: "" for c in MANIFEST_COLUMNS}
    row.update(dataset=key, folder=folder, path=str(path.relative_to(data_root)),
               size_bytes=size, **parse_ids(key, rel_in_dataset))
    row["_labels"] = []
    if do_hash:
        with open(path, "rb") as f:
            row["sha256"] = hashlib.file_digest(f, "sha256").hexdigest()
    if path.suffix.lower() == ".edf":
        row["is_edf"] = True
        try:
            h = read_edf_header(path, size)
            row.update(edf_ok=True, n_signals=h["n_signals"], fs_hz=h["fs_hz"],
                       duration_s=h["duration_s"], warning=h["warning"])
            row["_labels"] = h["labels"]
        except (ValueError, OSError) as e:
            row.update(edf_ok=False, error=str(e))
    else:
        row["is_edf"] = False
    return row


# ---------------------------------------------------------------- annotations

def chbmit_seizures(root: Path):
    """Seizures per EDF file name, from the chbXX-summary.txt files."""
    per_file, declared, notes = defaultdict(int), {}, []
    for summary in sorted(root.rglob("*-summary.txt")):
        current = None
        for line in summary.read_text(errors="replace").splitlines():
            m = re.match(r"\s*File Name:\s*(\S+)", line, re.I)
            if m:
                current = m.group(1)
                per_file[current] += 0
                continue
            m = re.match(r"\s*Number of Seizures in File:\s*(\d+)", line, re.I)
            if m and current:
                declared[current] = int(m.group(1))
                continue
            if current and re.match(r"\s*Seizure\s*\d*\s*Start Time:", line, re.I):
                per_file[current] += 1
    for name, n in sorted(declared.items()):
        if per_file[name] != n:
            notes.append(f"{name}: summary declares {n} seizures but lists {per_file[name]} start times")
    rws = root / "RECORDS-WITH-SEIZURES"
    if rws.exists():
        listed = {Path(x.strip()).name for x in rws.read_text().splitlines() if x.strip()}
        parsed = {f for f, n in per_file.items() if n > 0}
        if listed != parsed:
            notes.append(f"RECORDS-WITH-SEIZURES lists {len(listed)} files; summary files give "
                         f"{len(parsed)} files with seizures ({len(listed ^ parsed)} differ)")
        else:
            notes.append(f"RECORDS-WITH-SEIZURES matches the summary files ({len(listed)} files)")
    return dict(per_file), notes


def siena_seizures(root: Path):
    """Seizures per EDF file name, from the Seizures-list-PNxx.txt files."""
    per_file, notes = defaultdict(int), []
    lists = sorted(p for p in root.rglob("*.txt") if p.name.lower().startswith("seizures-list"))
    for lst in lists:
        current, starts, blocks = None, 0, 0
        for line in lst.read_text(errors="replace").splitlines():
            s = line.strip()
            m = re.match(r"file\s*name\s*:\s*(\S+)", s, re.I)
            if m:
                current = m.group(1)
                continue
            if re.match(r"seizure\s+n\s*\d", s, re.I):
                blocks += 1
                continue
            if re.match(r"(seizure\s+)?start\s+time\s*:", s, re.I):
                starts += 1
                per_file[current or f"{lst.name}:unknown file"] += 1
        if blocks != starts:
            notes.append(f"{lst.name}: {blocks} 'Seizure n' entries but {starts} start times")
    if not lists:
        notes.append("no Seizures-list files found")
    return dict(per_file), notes


def read_tuh_csv(path: Path):
    with open(path, newline="", errors="replace") as f:
        lines = [x for x in f if x.strip() and not x.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


def tuh_events(path: Path, keep) -> set:
    """Unique (start, stop, label) events in a TUH annotation file."""
    events = set()
    for r in read_tuh_csv(path):
        label = (r.get("label") or "").strip().lower()
        if keep(label):
            events.add((r.get("start_time", "").strip(), r.get("stop_time", "").strip(), label))
    return events


# ---------------------------------------------------------------- summary

def fingerprint(rows) -> str:
    lines = sorted(f"{r['path']},{r['size_bytes']},{r['sha256']}" for r in rows)
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def summarize(rows, data_root: Path, do_hash: bool):
    by_ds = defaultdict(list)
    for r in rows:
        by_ds[r["dataset"]].append(r)

    notes = defaultdict(list)
    extras = {}

    # Seizure counts per EDF
    edf_by_name = {}
    for r in rows:
        if r["is_edf"]:
            edf_by_name[(r["dataset"], Path(r["path"]).name.lower())] = r

    for folder in {r["folder"] for r in by_ds.get("chbmit", [])}:
        per_file, n = chbmit_seizures(data_root / folder)
        notes["chbmit"] += n
        for name, count in per_file.items():
            r = edf_by_name.get(("chbmit", name.lower()))
            if r:
                r["n_seizures"] = count
            elif count:
                notes["chbmit"].append(f"{name}: listed with {count} seizures but no matching EDF found")
        notes["chbmit"].append("chb01 and chb21 are the same subject (per the CHB-MIT documentation); "
                               "group them as one patient for cross-patient splits")

    siena_edfs = [r for r in by_ds.get("siena", []) if r["is_edf"]]
    siena_by_patient = defaultdict(list)
    for r in siena_edfs:
        r["n_seizures"] = 0
        siena_by_patient[r["patient"]].append(r)
    for folder in {r["folder"] for r in by_ds.get("siena", [])}:
        per_file, n = siena_seizures(data_root / folder)
        notes["siena"] += n
        for name, count in sorted(per_file.items()):
            r, how = edf_by_name.get(("siena", name.lower())), ""
            fixed = re.sub(r"^pno", "pn0", name.lower())  # letter O typed for zero, e.g. PNO6
            if r is None and fixed != name.lower():
                r = edf_by_name.get(("siena", fixed))
                how = "letter O typed for zero"
            if r is None:  # e.g. "PN01.edf" or "PN11-.edf" for a patient with a single EDF
                m = re.match(r"pn\d+", fixed)
                candidates = siena_by_patient.get(m.group(0).upper(), []) if m else []
                if len(candidates) == 1:
                    r, how = candidates[0], "only EDF for this patient"
            if r is None:
                notes["siena"].append(f"{name}: listed with {count} seizures but no matching EDF found")
                continue
            r["n_seizures"] += count
            if how:
                notes["siena"].append(f"Seizure list names '{name}'; matched to "
                                      f"{Path(r['path']).name} ({how})")

    missing_csv_bi = 0
    for r in by_ds.get("tusz", []):
        if r["is_edf"]:
            ann = data_root / Path(r["path"]).with_suffix(".csv_bi")
            if ann.exists():
                r["n_seizures"] = len(tuh_events(ann, lambda lab: lab == "seiz"))
            else:
                missing_csv_bi += 1
    if by_ds.get("tusz"):
        notes["tusz"].append(f"EDF files without a .csv_bi annotation file: {missing_csv_bi}")

    artifact_labels, tuar_seiz_recordings, missing_art = Counter(), 0, 0
    for r in by_ds.get("tuar", []):
        if not r["is_edf"]:
            continue
        stem = data_root / Path(r["path"]).with_suffix("")
        art, seiz = Path(f"{stem}.csv"), Path(f"{stem}_seiz.csv")
        if art.exists():
            for _, _, label in tuh_events(art, lambda lab: lab not in ("", "bckg")):
                artifact_labels[label] += 1
        else:
            missing_art += 1
        if seiz.exists():
            n = len({(a, b) for a, b, _ in tuh_events(seiz, lambda lab: lab not in ("", "bckg"))})
            r["n_seizures"] = n
            tuar_seiz_recordings += n > 0
    if by_ds.get("tuar"):
        notes["tuar"].append(f"EDF files without an artifact .csv: {missing_art}")
        notes["tuar"].append(f"Recordings with seizure annotations (_seiz.csv): {tuar_seiz_recordings}")
        notes["tuar"].append("Artifact events by label: " + (", ".join(
            f"{k} {v}" for k, v in sorted(artifact_labels.items())) or "none"))

    for r in by_ds.get("mental_arith", []):
        if r["is_edf"]:
            r["n_seizures"] = 0

    # Per-dataset counts
    summary = {}
    for key in sorted(by_ds):
        ds = by_ds[key]
        edfs = [r for r in ds if r["is_edf"]]
        ok = [r for r in edfs if r["edf_ok"] is True]
        patients = {r["patient"] for r in edfs if r["patient"]}
        seiz_known = [r for r in edfs if r["n_seizures"] != ""]
        summary[key] = {
            "folders": sorted({r["folder"] for r in ds}),
            "files": len(ds),
            "bytes": sum(r["size_bytes"] for r in ds),
            "edf_files": len(edfs),
            "edf_headers_failed": len(edfs) - len(ok),
            "edf_warnings": sum(1 for r in ok if r["warning"]),
            "patients": len(patients),
            "hours": round(sum(float(r["duration_s"]) for r in ok) / 3600, 2),
            "seizures": sum(int(r["n_seizures"]) for r in seiz_known) if seiz_known else None,
            "recordings_with_seizures": sum(1 for r in seiz_known if int(r["n_seizures"]) > 0),
            "patients_with_seizures": len({r["patient"] for r in seiz_known
                                           if int(r["n_seizures"]) > 0 and r["patient"]}),
            "sampling_rates_hz": {str(k): v for k, v in sorted(
                Counter(r["fs_hz"] for r in ok).items(), key=lambda kv: -kv[1])},
            "unparsed_patient_ids": sum(1 for r in edfs if not r["patient"]),
            "fingerprint": fingerprint(ds) if do_hash else None,
        }

    # TUSZ splits, montages and patients without seizures
    tusz = [r for r in by_ds.get("tusz", []) if r["is_edf"]]
    if tusz:
        splits = defaultdict(set)
        for r in tusz:
            splits[r["patient"]].add(r["split"])
        multi = sorted(p for p, s in splits.items() if len(s) > 1)
        per_split = Counter(s for sp in splits.values() for s in sp)
        seiz_patients = {r["patient"] for r in tusz if r["n_seizures"] not in ("", 0)}
        extras["tusz"] = {
            "patients_per_split": dict(sorted(per_split.items())),
            "patients_in_more_than_one_split": multi,
            "recordings_per_montage": dict(sorted(Counter(r["montage"] for r in tusz).items())),
            "patients_without_seizures": len(set(splits) - seiz_patients),
        }
        notes["tusz"].append(f"Patients in more than one official split: {len(multi)}"
                             + (f" ({', '.join(multi[:10])}{', ...' if len(multi) > 10 else ''})" if multi else ""))
        notes["tusz"].append(f"Patients with no annotated seizures (false-alarm set under D-5): "
                             f"{extras['tusz']['patients_without_seizures']}")

    # TUAR / TUSZ patient overlap
    overlap = []
    tuar_patients = {r["patient"] for r in by_ds.get("tuar", []) if r["is_edf"] and r["patient"]}
    if tuar_patients and tusz:
        tusz_splits = defaultdict(set)
        for r in tusz:
            tusz_splits[r["patient"]].add(r["split"])
        overlap = [(p, ";".join(sorted(tusz_splits[p]))) for p in sorted(tuar_patients & set(tusz_splits))]
        notes["tuar"].append(f"Patients also in TUSZ: {len(overlap)} of {len(tuar_patients)} "
                             "(listed in tuar_tusz_overlap.csv)")
    return summary, extras, notes, overlap


# ---------------------------------------------------------------- previous run

def load_previous(out_dir: Path):
    man, js = out_dir / "data_manifest.csv", out_dir / "data_audit_summary.json"
    if not (man.exists() and js.exists()):
        return None
    with open(man, newline="") as f:
        files = {r["path"]: (r["size_bytes"], r["sha256"]) for r in csv.DictReader(f)}
    prev = json.loads(js.read_text())
    if prev.get("quick"):
        return None
    return {"files": files, "summary": prev.get("datasets", {}), "generated": prev.get("generated")}


def compare(prev, rows, summary):
    if prev is None:
        return "PENDING", "No previous full run to compare with. Run the script again to complete VT-01."
    now = {r["path"]: (str(r["size_bytes"]), r["sha256"]) for r in rows}
    added = sorted(set(now) - set(prev["files"]))
    removed = sorted(set(prev["files"]) - set(now))
    changed = sorted(p for p in set(now) & set(prev["files"]) if now[p] != prev["files"][p])
    count_keys = ["files", "edf_files", "edf_headers_failed", "patients", "hours", "seizures",
                  "recordings_with_seizures", "patients_with_seizures", "fingerprint"]
    count_diffs = [f"{ds}.{k}: {prev['summary'].get(ds, {}).get(k)} -> {summary[ds].get(k)}"
                   for ds in summary for k in count_keys
                   if prev["summary"].get(ds, {}).get(k) != summary[ds].get(k)]
    if not (added or removed or changed or count_diffs):
        return "PASS", f"Identical to the previous run ({prev['generated']}): same checksums and counts."
    detail = [f"Compared with the previous run ({prev['generated']}):",
              f"{len(added)} files added, {len(removed)} removed, {len(changed)} changed."]
    detail += [f"Changed: {p}" for p in changed[:20]]
    detail += count_diffs[:20]
    return "FAIL", "<br>".join(detail)


# ---------------------------------------------------------------- outputs

def git_info():
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                                capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                               capture_output=True, text=True, check=True).stdout.strip()
        return commit + (" (uncommitted changes)" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def write_outputs(out_dir, rows, summary, extras, notes, overlap, hidden, do_hash, check, generated):
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "data_manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in sorted(rows, key=lambda r: r["path"]):
            w.writerow(r)

    labels = Counter()
    for r in rows:
        for label in set(r["_labels"]):
            labels[(r["dataset"], label)] += 1
    with open(out_dir / "channel_labels.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["dataset", "label", "n_recordings"])
        for (ds, label), n in sorted(labels.items()):
            w.writerow([ds, label, n])

    with open(out_dir / "tuar_tusz_overlap.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["patient", "tusz_splits"])
        w.writerows(overlap)

    (out_dir / "data_audit_summary.json").write_text(json.dumps(
        {"generated": generated, "quick": not do_hash, "datasets": summary, "extras": extras},
        indent=2))

    # Markdown report
    missing = [k for k in DATASETS if k not in summary]
    failed = [r for r in rows if r["is_edf"] and r["edf_ok"] is False]
    status, detail = check
    lines = [
        "# Data audit (VT-01)",
        "",
        f"Generated {generated} · commit {git_info()} · Python {platform.python_version()} "
        f"· {'full run' if do_hash else 'QUICK RUN (no checksums, not valid VT-01 evidence)'}",
        "",
        "## VT-01 checklist",
        "",
        "| Criterion | Result |",
        "|---|---|",
        "| Manifest covers all five datasets | "
        + ("PASS" if not missing else f"FAIL (missing: {', '.join(missing)})") + " |",
        "| Every EDF header opens, or the failure is logged with a reason | "
        f"PASS ({len(failed)} failure{'' if len(failed) == 1 else 's'} logged"
        + (" below) |" if failed else ") |"),
        f"| Second run gives identical checksums and counts | {status}: {detail} |",
        "",
        "## Summary",
        "",
        "| Dataset | Files | Size (GB) | EDF | Headers failed | Patients | Hours | Seizures "
        "| Patients with seizures | Sampling rates (Hz: recordings) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for ds, s in summary.items():
        rates = ", ".join(f"{k}: {v}" for k, v in list(s["sampling_rates_hz"].items())[:4])
        if len(s["sampling_rates_hz"]) > 4:
            rates += ", ..."
        seiz = "n/a" if s["seizures"] is None else s["seizures"]
        lines.append(f"| {ds} | {s['files']} | {s['bytes'] / 1e9:.1f} | {s['edf_files']} "
                     f"| {s['edf_headers_failed']} | {s['patients']} | {s['hours']} | {seiz} "
                     f"| {s['patients_with_seizures']} | {rates} |")
    lines += ["", f"Hidden files skipped (for example .DS_Store): {hidden}", "", "## Notes", ""]
    for ds in summary:
        extra = []
        if summary[ds]["edf_warnings"]:
            extra.append(f"EDF files with header warnings: {summary[ds]['edf_warnings']} "
                         "(see the warning column in data_manifest.csv)")
        if summary[ds]["unparsed_patient_ids"]:
            extra.append(f"EDF files with no recognizable patient ID: {summary[ds]['unparsed_patient_ids']}")
        items = notes.get(ds, []) + extra
        if items:
            lines.append(f"**{ds}**")
            lines.append("")
            lines += [f"- {n}" for n in items]
            lines.append("")
    if failed:
        lines += ["## EDF header failures", "", "| File | Reason |", "|---|---|"]
        lines += [f"| {r['path']} | {r['error']} |" for r in failed]
        lines.append("")
    if do_hash:
        lines += ["## Dataset fingerprints", "",
                  "SHA-256 of each dataset's sorted list of (path, size, checksum). "
                  "Identical fingerprints mean identical files.", "",
                  "| Dataset | Fingerprint |", "|---|---|"]
        lines += [f"| {ds} | `{s['fingerprint']}` |" for ds, s in summary.items()]
    (out_dir / "data_audit.md").write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", type=Path, default=REPO / "data" / "raw")
    ap.add_argument("--out", type=Path, default=REPO / "results" / "d1")
    ap.add_argument("--quick", action="store_true", help="skip SHA-256 checksums")
    ap.add_argument("--workers", type=int, default=8, help="parallel file readers")
    args = ap.parse_args()

    if not args.data_root.is_dir():
        sys.exit(f"Data folder not found: {args.data_root}")
    do_hash = not args.quick
    out_dir = args.out if do_hash else args.out / "quick"
    generated = datetime.now().isoformat(timespec="seconds")

    items, hidden = find_files(args.data_root)
    total = sum(p.stat().st_size for _, _, p in items)
    print(f"{len(items)} files, {total / 1e9:.1f} GB under {args.data_root}")
    if do_hash:
        print("Computing SHA-256 checksums; this reads every byte and can take several minutes.")

    prev = load_previous(out_dir) if do_hash else None

    rows = []
    bar = tqdm(total=total, unit="B", unit_scale=True) if tqdm else None
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(process_file, it, args.data_root, do_hash) for it in items]
        for i, fut in enumerate(as_completed(futures), 1):
            row = fut.result()
            rows.append(row)
            if bar:
                bar.update(row["size_bytes"])
            elif i % 1000 == 0:
                print(f"  {i}/{len(items)} files")
    if bar:
        bar.close()

    summary, extras, notes, overlap = summarize(rows, args.data_root, do_hash)
    check = compare(prev, rows, summary) if do_hash else ("SKIPPED", "Quick run; checksums not computed.")
    write_outputs(out_dir, rows, summary, extras, notes, overlap, hidden, do_hash, check, generated)

    print()
    for ds, s in summary.items():
        seiz = "n/a" if s["seizures"] is None else s["seizures"]
        print(f"{ds:13s} patients {s['patients']:4d}  EDF {s['edf_files']:5d}  "
              f"hours {s['hours']:8.1f}  seizures {seiz}  header failures {s['edf_headers_failed']}")
    print(f"\nRun comparison: {check[0]}")
    print(f"Report: {out_dir / 'data_audit.md'}")


if __name__ == "__main__":
    main()
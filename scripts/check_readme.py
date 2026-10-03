"""VT-20 README check (docs/verification_plan.md, REQ-X1).

Checks the README against the course plan: data used, code written, tests run, verification
metrics and current model metrics. Every headline number in the README is compared with the
results file it comes from, and the stated number of tests with what pytest collects.

Usage, from the repo root with .venv active:
    python scripts/check_readme.py

Output: results/d2/readme_check.md (PASS only if every check passes)
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
NUM = re.compile(r"\d+\.\d{2,3}")


def first_number(path: Path, key: str, nth: int = 0) -> float | None:
    """The nth decimal number on the first line of a file containing key."""
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if key in line:
            nums = NUM.findall(line.split(key, 1)[1])
            return float(nums[nth]) if len(nums) > nth else None
    return None


def main():
    readme = (REPO / "README.md").read_text()
    checks = []

    def check(name, ok, detail):
        checks.append((name, bool(ok), detail))

    # sections the course plan requires
    for title, heading in (("Data used", "## Datasets"), ("Code written", "## Repository structure"),
                           ("Tests run", "## Tests"), ("Verification metrics", "## Verification and results"),
                           ("Current model metrics", "### Current model metrics")):
        check(f"Section: {title}", heading in readme, f"`{heading}`")

    # number of tests
    r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=REPO, capture_output=True, text=True)
    m = re.search(r"(\d+) tests? collected", r.stdout)
    n_tests = int(m.group(1)) if m else None
    check("Test count matches pytest", n_tests is not None and f"{n_tests} automated tests" in readme,
          f"pytest collects {n_tests}; README must say \"{n_tests} automated tests\"")

    # headline numbers against their results files
    res = REPO / "results"

    def number(name, value, fmt="{:.3f}"):
        if value is None:
            check(name, False, "results file or value not found")
            return
        s = fmt.format(value)
        check(name, s in readme, f"results file says {s}")

    d1 = res / "d1" / "lopo_summary.json"
    number("D1 cross-patient AUROC", json.loads(d1.read_text())["mean_patient_auroc"] if d1.exists() else None)
    d2 = res / "d2" / "d2_summary.json"
    number("D2 cross-patient AUROC", json.loads(d2.read_text())["mean_auroc"] if d2.exists() else None)
    number("Patient-specific AUROC", first_number(res / "d2" / "patient_specific.md", "Mean patient-specific AUROC"))
    number("Frozen design, development AUROC", first_number(res / "d2" / "personalized_dev_ctx10.md", "10 min context)"))
    number("SeizeIT2 dry run AUROC",
           first_number(res / "seizeit2_dev" / "personalized_seizeit2_dev.md", "| Other patients + this patient"))
    lock = res / "lockbox" / "seizeit2_lockbox_auroc.md"
    number("Lockbox AUROC, frozen design", first_number(lock, "| Frozen design"))
    number("Lockbox AUROC, other patients only", first_number(lock, "| Other patients only"))
    alarms = res / "lockbox" / "seizeit2_lockbox_alarms.md"
    if alarms.exists():
        row = next((l for l in alarms.read_text().splitlines() if "Frozen design" in l and "≤ 5" in l), "")
        frac = re.search(r"\((\d\.\d+)\)", row)
        far = NUM.findall(row.split(")", 1)[1]) if ")" in row else []
        number("Lockbox alarms, seizures warned (≤ 5)", float(frac.group(1)) * 100 if frac else None, "{:.0f}%")
        number("Lockbox alarms, false alarms per 24 h", float(far[0]) if far else None, "{:.2f}")
    else:
        check("Lockbox alarms", False, "results file not found")
    lc = res / "seizeit2_dev" / "learning_curve.csv"
    if lc.exists():
        rows = [x for x in csv.DictReader(open(lc)) if int(x["k"]) >= 1
                and x["auroc_personal"] not in ("", "nan") and x["auroc_general"] not in ("", "nan")]
        number("Learning device AUROC after ≥ 1 seizure", float(np.mean([float(x["auroc_personal"]) for x in rows])))
        number("Never-learning AUROC on the same steps", float(np.mean([float(x["auroc_general"]) for x in rows])))
    else:
        check("Learning curve", False, "results file not found")

    passed = all(ok for _, ok, _ in checks)
    lines = ["# VT-20 README check", "", f"Generated {datetime.now().isoformat(timespec='seconds')} with "
             "`scripts/check_readme.py`.", "", f"**Result: {'PASS' if passed else 'FAIL'}** "
             f"({sum(ok for _, ok, _ in checks)} of {len(checks)} checks)", "",
             "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {n} | {'pass' if ok else 'FAIL'} | {d} |" for n, ok, d in checks]
    out = res / "d2"
    out.mkdir(parents=True, exist_ok=True)
    (out / "readme_check.md").write_text("\n".join(lines) + "\n")
    for n, ok, d in checks:
        print(f"{'pass' if ok else 'FAIL'}  {n}: {d}")
    print(f"\nVT-20: {'PASS' if passed else 'FAIL'}; report: {out / 'readme_check.md'}")


if __name__ == "__main__":
    main()

# VT-20 README check

Generated 2026-10-04T23:43:16 with `scripts/check_readme.py`.

**Result: PASS** (17 of 17 checks)

| Check | Result | Detail |
|---|---|---|
| Section: Data used | pass | `## Datasets` |
| Section: Code written | pass | `## Repository structure` |
| Section: Tests run | pass | `## Tests` |
| Section: Verification metrics | pass | `## Verification and results` |
| Section: Current model metrics | pass | `### Current model metrics` |
| Test count matches pytest | pass | pytest collects 188; README must say "188 automated tests" |
| D1 cross-patient AUROC | pass | results file says 0.556 |
| D2 cross-patient AUROC | pass | results file says 0.614 |
| Patient-specific AUROC | pass | results file says 0.662 |
| Frozen design, development AUROC | pass | results file says 0.700 |
| SeizeIT2 dry run AUROC | pass | results file says 0.669 |
| Lockbox AUROC, frozen design | pass | results file says 0.621 |
| Lockbox AUROC, other patients only | pass | results file says 0.547 |
| Lockbox alarms, seizures warned (≤ 5) | pass | results file says 38% |
| Lockbox alarms, false alarms per 24 h | pass | results file says 5.83 |
| Learning device AUROC after ≥ 1 seizure | pass | results file says 0.606 |
| Never-learning AUROC on the same steps | pass | results file says 0.454 |

# SeizeIT2 lockbox: frozen design, alarms

Generated 2026-10-02T19:52:25 · seeds [0] · 20 patients · docs/evaluation_methods.md v1.13 (frozen design) and v1.17 (lockbox protocol).

Alarm part on a random subset of 20 of the 62 patients scored in the AUROC part (seed 0, evaluation methods v1.18): seizeit2:sub-004, seizeit2:sub-007, seizeit2:sub-011, seizeit2:sub-021, seizeit2:sub-026, seizeit2:sub-030, seizeit2:sub-047, seizeit2:sub-056, seizeit2:sub-059, seizeit2:sub-064, seizeit2:sub-066, seizeit2:sub-068, seizeit2:sub-072, seizeit2:sub-076, seizeit2:sub-082, seizeit2:sub-102, seizeit2:sub-111, seizeit2:sub-115, seizeit2:sub-119, seizeit2:sub-122.

| Model | Target | Seizures warned | False alarms per 24 h | Chance | p (vs chance) |
|---|---|---|---|---|---|
| Other patients only (frozen design's features and baseline) | ≤ 5 | 9/78 (0.12) | 4.88 | 0.096 | 0.338 |
| Other patients only (frozen design's features and baseline) | ≤ 1 | 5/78 (0.06) | 1.29 | 0.026 | 0.0559 |
| Frozen design: other patients + this patient | ≤ 5 | 30/78 (0.38) | 5.83 | 0.114 | 6.74e-10 |
| Frozen design: other patients + this patient | ≤ 1 | 14/78 (0.18) | 1.69 | 0.035 | 4.34e-07 |

# Personalized designs: alarm-level test (characterization)

Generated 2026-09-30T22:46:04 · seeds [0] · 14 patients · docs/evaluation_methods.md v1.5, Section 11.2. Thresholds chosen from each patient's training data only.

| Model | False-alarm target | Seizures warned | False alarms per 24 h | Chance probability | p (vs chance) | Patients with at least one seizure warned |
|---|---|---|---|---|---|---|
| Other patients only (frozen design's features and baseline) | ≤ 5 | 0.09 | 5.13 | 0.101 | 0.712 (median over seeds) | 6.0 of 14 |
| Other patients only (frozen design's features and baseline) | ≤ 1 | 0.03 | 1.51 | 0.031 | 0.595 (median over seeds) | 4.0 of 14 |
| Frozen design: other patients + this patient | ≤ 5 | 0.46 | 4.58 | 0.091 | 2.54e-28 (median over seeds) | 11.0 of 14 |
| Frozen design: other patients + this patient | ≤ 1 | 0.20 | 1.71 | 0.035 | 1.74e-13 (median over seeds) | 6.0 of 14 |

## Per patient (target ≤ 5 per 24 h, mean over seeds)

| Patient | Seizures | Other patients only (frozen design's features and baseline): warned / FAR | Frozen design: other patients + this patient: warned / FAR |
|---|---|---|---|
| seizeit2:sub-001 | 4 | 2.0/4 · 6.1 | 1.0/4 · 5.5 |
| seizeit2:sub-002 | 14 | 2.0/14 · 5.0 | 5.0/14 · 3.0 |
| seizeit2:sub-005 | 1 | 0.0/1 · 5.0 | 0.0/1 · 2.7 |
| seizeit2:sub-029 | 4 | 1.0/4 · 5.8 | 1.0/4 · 5.6 |
| seizeit2:sub-034 | 23 | 1.0/23 · 9.0 | 17.0/23 · 4.5 |
| seizeit2:sub-053 | 1 | 0.0/1 · 7.2 | 0.0/1 · 3.6 |
| seizeit2:sub-065 | 1 | 0.0/1 · 3.3 | 0.0/1 · 4.0 |
| seizeit2:sub-073 | 47 | 4.0/47 · 5.1 | 27.0/47 · 3.4 |
| seizeit2:sub-074 | 9 | 0.0/9 · 4.6 | 2.0/9 · 5.8 |
| seizeit2:sub-086 | 2 | 0.0/2 · 7.4 | 1.0/2 · 11.6 |
| seizeit2:sub-100 | 2 | 0.0/2 · 3.7 | 1.0/2 · 2.7 |
| seizeit2:sub-103 | 10 | 0.0/10 · 2.4 | 4.0/10 · 4.9 |
| seizeit2:sub-112 | 7 | 0.0/7 · 4.0 | 1.0/7 · 5.4 |
| seizeit2:sub-113 | 9 | 2.0/9 · 5.4 | 1.0/9 · 2.4 |

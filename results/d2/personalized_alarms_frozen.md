# Personalized designs: alarm-level test (characterization)

Generated 2026-09-29T21:35:15 · seeds [0, 1] · 22 patients · docs/evaluation_methods.md v1.5, Section 11.2. Thresholds chosen from each patient's training data only.

| Model | False-alarm target | Seizures warned | False alarms per 24 h | Chance probability | p (vs chance) | Patients with at least one seizure warned |
|---|---|---|---|---|---|---|
| Other patients only (frozen design's features and baseline) | ≤ 5 | 0.04 | 4.76 | 0.094 | 0.979 (median over seeds) | 3.5 of 22 |
| Other patients only (frozen design's features and baseline) | ≤ 1 | 0.03 | 1.76 | 0.036 | 0.749 (median over seeds) | 2.0 of 22 |
| Frozen design: other patients + this patient | ≤ 5 | 0.16 | 3.43 | 0.069 | 0.00277 (median over seeds) | 8.5 of 22 |
| Frozen design: other patients + this patient | ≤ 1 | 0.09 | 1.41 | 0.029 | 0.00296 (median over seeds) | 5.0 of 22 |

## Per patient (target ≤ 5 per 24 h, mean over seeds)

| Patient | Seizures | Other patients only (frozen design's features and baseline): warned / FAR | Frozen design: other patients + this patient: warned / FAR |
|---|---|---|---|
| chbmit:chb01 | 10 | 0.0/10 · 3.2 | 0.0/10 · 1.3 |
| chbmit:chb02 | 1 | 0.0/1 · 0.0 | 0.0/1 · 0.0 |
| chbmit:chb03 | 6 | 0.5/6 · 5.7 | 0.0/6 · 1.8 |
| chbmit:chb04 | 4 | 0.0/4 · 3.6 | 0.0/4 · 3.7 |
| chbmit:chb05 | 4 | 0.0/4 · 0.0 | 0.0/4 · 4.2 |
| chbmit:chb06 | 10 | 0.5/10 · 2.9 | 0.0/10 · 0.5 |
| chbmit:chb07 | 2 | 0.0/2 · 15.5 | 0.5/2 · 2.5 |
| chbmit:chb09 | 4 | 0.0/4 · 6.2 | 0.0/4 · 5.9 |
| chbmit:chb10 | 6 | 0.0/6 · 6.0 | 1.5/6 · 2.5 |
| chbmit:chb13 | 5 | 0.0/5 · 2.4 | 0.5/5 · 1.6 |
| chbmit:chb14 | 6 | 0.0/6 · 5.1 | 0.0/6 · 2.6 |
| chbmit:chb15 | 9 | 0.5/9 · 0.0 | 0.0/9 · 0.0 |
| chbmit:chb16 | 5 | 0.0/5 · 6.4 | 1.0/5 · 0.0 |
| chbmit:chb17 | 2 | 0.0/2 · 7.1 | 0.0/2 · 1.4 |
| chbmit:chb18 | 3 | 0.0/3 · 9.7 | 0.0/3 · 9.1 |
| chbmit:chb19 | 2 | 0.0/2 · 0.4 | 0.5/2 · 0.4 |
| chbmit:chb20 | 2 | 0.5/2 · 3.2 | 2.0/2 · 11.1 |
| chbmit:chb22 | 1 | 0.0/1 · 0.0 | 0.0/1 · 4.2 |
| chbmit:chb23 | 4 | 0.0/4 · 0.0 | 4.0/4 · 6.3 |
| siena:PN01 | 2 | 0.5/2 · 11.9 | 1.0/2 · 5.9 |
| siena:PN03 | 1 | 0.0/1 · 3.9 | 1.0/1 · 11.6 |
| siena:PN14 | 4 | 1.5/4 · 6.2 | 2.5/4 · 6.2 |

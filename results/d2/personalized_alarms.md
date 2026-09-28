# Personalized designs: alarm-level test (characterization)

Generated 2026-09-28T02:30:47 · seeds [0, 1, 2, 3, 4] · 22 patients · docs/evaluation_methods.md v1.5, Section 11.2. Thresholds chosen from each patient's training data only.

| Model | False-alarm target | Seizures warned | False alarms per 24 h | Chance probability | p (vs chance) | Patients with at least one seizure warned |
|---|---|---|---|---|---|---|
| Other patients only, EEG + time of day | ≤ 5 | 0.26 | 6.87 | 0.133 | 0.000809 (median over seeds) | 14.0 of 22 |
| Other patients only, EEG + time of day | ≤ 1 | 0.17 | 2.18 | 0.044 | 5.88e-06 (median over seeds) | 9.0 of 22 |
| Other patients + this patient, EEG + time of day | ≤ 5 | 0.27 | 6.02 | 0.118 | 5.69e-05 (median over seeds) | 14.0 of 22 |
| Other patients + this patient, EEG + time of day | ≤ 1 | 0.18 | 2.28 | 0.046 | 2.23e-06 (median over seeds) | 10.4 of 22 |
| This patient only, EEG + 10 min context + time of day | ≤ 5 | 0.18 | 4.92 | 0.097 | 0.0374 (median over seeds) | 10.2 of 22 |
| This patient only, EEG + 10 min context + time of day | ≤ 1 | 0.15 | 1.54 | 0.032 | 2.93e-06 (median over seeds) | 8.8 of 22 |

## Per patient (target ≤ 5 per 24 h, mean over seeds)

| Patient | Seizures | Other patients only, EEG + time of day: warned / FAR | Other patients + this patient, EEG + time of day: warned / FAR | This patient only, EEG + 10 min context + time of day: warned / FAR |
|---|---|---|---|---|
| chbmit:chb01 | 10 | 1.6/10 · 5.8 | 2.8/10 · 3.8 | 3.4/10 · 2.9 |
| chbmit:chb02 | 1 | 1.0/1 · 20.4 | 1.0/1 · 5.7 | 1.0/1 · 0.0 |
| chbmit:chb03 | 6 | 1.2/6 · 7.1 | 0.6/6 · 7.2 | 0.0/6 · 0.7 |
| chbmit:chb04 | 4 | 1.0/4 · 4.9 | 0.0/4 · 4.3 | 1.6/4 · 10.3 |
| chbmit:chb05 | 4 | 1.6/4 · 5.4 | 2.4/4 · 7.1 | 2.0/4 · 8.4 |
| chbmit:chb06 | 10 | 0.4/10 · 6.6 | 0.0/10 · 3.5 | 0.0/10 · 1.7 |
| chbmit:chb07 | 2 | 0.6/2 · 6.9 | 0.6/2 · 7.0 | 1.0/2 · 4.5 |
| chbmit:chb09 | 4 | 0.0/4 · 7.5 | 0.2/4 · 7.9 | 0.0/4 · 3.1 |
| chbmit:chb10 | 6 | 2.0/6 · 7.5 | 0.0/6 · 5.0 | 0.2/6 · 0.8 |
| chbmit:chb13 | 5 | 1.2/5 · 9.3 | 1.8/5 · 5.4 | 0.0/5 · 1.6 |
| chbmit:chb14 | 6 | 0.0/6 · 10.2 | 1.0/6 · 0.0 | 0.0/6 · 0.0 |
| chbmit:chb15 | 9 | 5.6/9 · 21.6 | 3.6/9 · 0.0 | 1.0/9 · 0.0 |
| chbmit:chb16 | 5 | 0.0/5 · 6.9 | 2.0/5 · 5.1 | 2.0/5 · 0.0 |
| chbmit:chb17 | 2 | 0.6/2 · 6.8 | 0.0/2 · 2.8 | 0.0/2 · 0.0 |
| chbmit:chb18 | 3 | 2.0/3 · 6.6 | 1.0/3 · 10.7 | 0.0/3 · 1.9 |
| chbmit:chb19 | 2 | 0.0/2 · 12.5 | 0.6/2 · 10.2 | 0.0/2 · 0.9 |
| chbmit:chb20 | 2 | 0.2/2 · 1.9 | 1.6/2 · 14.6 | 1.8/2 · 15.2 |
| chbmit:chb22 | 1 | 0.0/1 · 0.0 | 0.0/1 · 5.1 | 0.0/1 · 8.5 |
| chbmit:chb23 | 4 | 2.0/4 · 8.0 | 2.0/4 · 9.3 | 1.0/4 · 4.2 |
| siena:PN01 | 2 | 2.0/2 · 14.2 | 2.0/2 · 14.2 | 2.0/2 · 35.6 |
| siena:PN03 | 1 | 0.4/1 · 0.0 | 0.0/1 · 0.0 | 0.0/1 · 0.0 |
| siena:PN14 | 4 | 1.0/4 · 4.2 | 1.8/4 · 11.6 | 0.0/4 · 0.0 |

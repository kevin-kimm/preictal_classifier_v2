# D1 baseline, leave-one-patient-out (VT-08 to VT-13)

Generated 2026-09-26T11:42:14 · commit 37c1524 (uncommitted code changes) · Python 3.13.2 · seeds [0, 1, 2, 3, 4] · feature version d1-v1-284c11e880

Method: docs/evaluation_methods.md. Unit tests (features, alarms, folds, metrics): PASS, 38 passed in 0.97s.

## Results

| Test | Result |
|---|---|
| VT-08 patient separation | PASS: 0 problems in 125 folds; no per-patient normalization in D1 |
| VT-09 reproducibility | PASS: AUROC difference 0.0000 on a repeated fold; all five seeds reported |
| VT-10 threshold selection | PASS: every threshold chosen on inner validation patients and fixed before the test patient was scored |
| VT-11 cross-patient classification | PASS: mean per-patient AUROC 0.556 ± 0.007 across seeds, 95% CI 0.502–0.616; 25 of 25 test patients completed. Nice to have (≥ 0.65): not met |
| VT-12 channel subsets (characterization) | Mean AUROC: all channels 0.556, random half 0.573, Cyton 6 derivations 0.570 |
| VT-13 baseline alarms | FAIL: 10.61 false alarms per 24 h (target ≤ 10) |

## Per seed

| Seed | Mean patient AUROC | Pooled AUROC | Macro F1 | Sensitivity | FAR / 24 h | Time in warning | Median warning | Chance probability | p (vs chance) |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0.553 | 0.499 | 0.299 | 25/111 (0.23) | 9.93 | 0.205 | 12.0 min | 0.186 | 0.176 |
| 1 | 0.554 | 0.504 | 0.307 | 20/111 (0.18) | 8.96 | 0.182 | 15.6 min | 0.170 | 0.425 |
| 2 | 0.564 | 0.532 | 0.309 | 26/111 (0.23) | 12.22 | 0.243 | 16.7 min | 0.224 | 0.437 |
| 3 | 0.545 | 0.502 | 0.309 | 24/111 (0.22) | 10.77 | 0.216 | 18.2 min | 0.201 | 0.376 |
| 4 | 0.564 | 0.523 | 0.308 | 20/111 (0.18) | 11.15 | 0.222 | 16.8 min | 0.207 | 0.789 |

## Per test patient (mean over seeds)

| Patient | Dataset | AUROC | Sensitivity | FAR / 24 h |
|---|---|---|---|---|
| chbmit:chb01 | chbmit | 0.484 | 0.12 | 6.66 |
| chbmit:chb02 | chbmit | 0.372 | 0.10 | 11.45 |
| chbmit:chb03 | chbmit | 0.493 | 0.47 | 17.44 |
| chbmit:chb04 | chbmit | 0.367 | 0.55 | 18.67 |
| chbmit:chb05 | chbmit | 0.574 | 0.28 | 10.24 |
| chbmit:chb06 | chbmit | 0.430 | 0.02 | 0.78 |
| chbmit:chb07 | chbmit | 0.545 | 0.00 | 1.69 |
| chbmit:chb08 | chbmit | 0.395 | 0.16 | 16.83 |
| chbmit:chb09 | chbmit | 0.344 | 0.05 | 5.63 |
| chbmit:chb10 | chbmit | 0.635 | 0.00 | 0.41 |
| chbmit:chb11 | chbmit | 0.565 | 0.20 | 10.36 |
| chbmit:chb13 | chbmit | 0.629 | 0.40 | 12.42 |
| chbmit:chb14 | chbmit | 0.474 | 0.10 | 4.84 |
| chbmit:chb15 | chbmit | 0.503 | 0.00 | 2.07 |
| chbmit:chb16 | chbmit | 0.426 | 0.12 | 6.45 |
| chbmit:chb17 | chbmit | 0.666 | 0.27 | 7.22 |
| chbmit:chb18 | chbmit | 0.560 | 0.10 | 0.29 |
| chbmit:chb19 | chbmit | 0.532 | 0.10 | 7.20 |
| chbmit:chb20 | chbmit | 0.723 | 0.08 | 2.70 |
| chbmit:chb22 | chbmit | 0.649 | 0.30 | 10.01 |
| chbmit:chb23 | chbmit | 0.782 | 0.00 | 1.00 |
| siena:PN01 | siena | 0.970 | 1.00 | 40.88 |
| siena:PN03 | siena | 0.592 | 1.00 | 47.07 |
| siena:PN07 | siena | 0.438 | 1.00 | 38.00 |
| siena:PN14 | siena | 0.751 | 0.80 | 44.11 |

## False-alarm test sets

Models trained on all CHB-MIT and Siena patients, scored on interictal time only.

| Seed | Dataset | Hours | False alarms | FAR / 24 h | Patients | Median patient FAR | 90th pct |
|---|---|---|---|---|---|---|---|
| 0 | tusz | 1014.04 | 2674 | 63.29 | 592 | 68.85 | 163.88 |
| 0 | mental_arith | 1.87 | 0 | 0.00 | 36 | nan | nan |
| 1 | tusz | 1014.04 | 3148 | 74.51 | 592 | 76.81 | 173.26 |
| 1 | mental_arith | 1.87 | 2 | 25.66 | 36 | nan | nan |
| 2 | tusz | 1014.04 | 3087 | 73.06 | 592 | 73.77 | 172.50 |
| 2 | mental_arith | 1.87 | 1 | 12.83 | 36 | nan | nan |
| 3 | tusz | 1014.04 | 2683 | 63.50 | 592 | 70.04 | 158.37 |
| 3 | mental_arith | 1.87 | 0 | 0.00 | 36 | nan | nan |
| 4 | tusz | 1014.04 | 3126 | 73.99 | 592 | 73.89 | 173.94 |
| 4 | mental_arith | 1.87 | 2 | 25.66 | 36 | nan | nan |

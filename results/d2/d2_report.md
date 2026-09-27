# D2: experiments 1-4 and alarm logic

Generated 2026-09-26T23:03:04 · commit 29c2228 · Python 3.13.2 · seeds [0, 1, 2, 3, 4] · steps ['normalize', 'context', 'clock', 'tusz', 'model'] · feature version d1-v1-284c11e880 · 381 min

Method: docs/evaluation_methods.md v1.2. Every choice was made per fold on inner validation patients; no test result was used.

## Results

| Test | Result |
|---|---|
| VT-15 improvement over D1 | FAIL: mean per-patient AUROC 0.614 ± 0.007 (95% CI 0.529–0.702) vs D1 0.556 on the same seeds: +10.5% (target +15%). Wilcoxon p = 0.127. Nice to have (≥ 0.75): not met |
| VT-17 event-level performance | FAIL: sensitivity 0.16 (target ≥ 0.80), 5.84 false alarms per 24 h (target ≤ 5), largest p vs chance 0.256 |
| Reference: clock-only model | mean AUROC 0.691 |
| D2 without time-of-day features | mean AUROC 0.528 |

## Setups chosen (per test patient fold)

| Setup | Folds |
|---|---|
| norm=off ctx=0min clock=on tusz=off model=hgb | 9 |
| norm=off ctx=10min clock=on tusz=off model=hgb | 5 |
| norm=on ctx=10min clock=on tusz=off model=hgb | 5 |
| norm=off ctx=2min clock=on tusz=off model=hgb | 2 |
| norm=off ctx=10min clock=on tusz=on model=hgb | 2 |
| norm=off ctx=2min clock=on tusz=off model=nn | 1 |
| norm=off ctx=0min clock=on tusz=on model=hgb | 1 |

Setup chosen on all patients (used for the false-alarm sets): norm=off ctx=0min clock=on tusz=off model=hgb, alarm smoothing 36, persistence 6.
Dataset check: a model can tell TUSZ from CHB-MIT/Siena interictal windows with AUROC 0.959 (0.5 = indistinguishable).

## Per seed

| Seed | AUROC | Without clock | Clock only | Sensitivity | FAR / 24 h | Time in warning | Chance prob. | p |
|---|---|---|---|---|---|---|---|---|
| 0 | 0.605 | 0.513 | 0.697 | 18/111 (0.16) | 5.32 | 0.110 | 0.105 | 0.0402 |
| 1 | 0.622 | 0.514 | 0.701 | 15/111 (0.14) | 5.70 | 0.115 | 0.112 | 0.256 |
| 2 | 0.609 | 0.542 | 0.686 | 17/111 (0.15) | 6.44 | 0.130 | 0.125 | 0.224 |
| 3 | 0.615 | 0.528 | 0.689 | 22/111 (0.20) | 5.73 | 0.119 | 0.112 | 0.00567 |
| 4 | 0.620 | 0.543 | 0.681 | 17/111 (0.15) | 6.01 | 0.121 | 0.117 | 0.153 |

## Per test patient (mean over seeds)

| Patient | D1 AUROC | D2 AUROC | Clock only | Sensitivity | FAR / 24 h |
|---|---|---|---|---|---|
| chbmit:chb08 | 0.395 | 0.105 | 0.200 | 0.16 | 12.06 |
| chbmit:chb04 | 0.367 | 0.316 | 0.348 | 0.20 | 9.12 |
| chbmit:chb09 | 0.344 | 0.349 | 0.519 | 0.05 | 6.14 |
| chbmit:chb14 | 0.474 | 0.376 | 0.504 | 0.03 | 0.84 |
| chbmit:chb20 | 0.723 | 0.385 | 0.597 | 0.00 | 4.64 |
| chbmit:chb16 | 0.426 | 0.428 | 0.453 | 0.00 | 1.47 |
| chbmit:chb03 | 0.493 | 0.442 | 0.562 | 0.17 | 4.43 |
| chbmit:chb13 | 0.629 | 0.467 | 0.475 | 0.32 | 8.76 |
| chbmit:chb06 | 0.430 | 0.487 | 0.675 | 0.06 | 0.62 |
| chbmit:chb22 | 0.649 | 0.517 | 0.384 | 0.00 | 7.26 |
| chbmit:chb01 | 0.484 | 0.600 | 0.820 | 0.08 | 3.19 |
| chbmit:chb17 | 0.666 | 0.631 | 0.602 | 0.00 | 3.73 |
| chbmit:chb05 | 0.574 | 0.641 | 0.799 | 0.08 | 4.39 |
| chbmit:chb10 | 0.635 | 0.655 | 0.767 | 0.03 | 0.51 |
| chbmit:chb19 | 0.532 | 0.671 | 0.854 | 0.00 | 3.85 |
| chbmit:chb15 | 0.503 | 0.703 | 0.557 | 0.00 | 0.28 |
| chbmit:chb02 | 0.372 | 0.715 | 1.000 | 0.40 | 4.80 |
| siena:PN14 | 0.751 | 0.767 | 0.797 | 0.70 | 31.32 |
| siena:PN07 | 0.438 | 0.774 | 1.000 | 0.00 | 5.26 |
| chbmit:chb18 | 0.560 | 0.804 | 0.914 | 0.15 | 0.43 |
| siena:PN03 | 0.592 | 0.830 | 1.000 | 1.00 | 35.04 |
| chbmit:chb23 | 0.782 | 0.857 | 0.931 | 0.48 | 3.21 |
| chbmit:chb07 | 0.545 | 0.902 | 0.947 | 0.20 | 1.25 |
| chbmit:chb11 | 0.565 | 0.937 | 0.780 | 0.00 | 0.71 |
| siena:PN01 | 0.970 | 0.997 | 0.781 | 1.00 | 22.75 |

## False-alarm sets (setup chosen on all patients)

The setup chosen on all patients uses the time of day, which these recordings don't have, so they were scored with the same setup without it (norm=off ctx=0min clock=off tusz=off model=hgb).

| Seed | Set | Hours | False alarms | FAR / 24 h |
|---|---|---|---|---|
| 0 | tusz (held-out half) | 557.15 | 1154 | 49.71 |
| 0 | mental_arith | 1.87 | 0 | 0.00 |
| 1 | tusz (held-out half) | 557.15 | 1378 | 59.36 |
| 1 | mental_arith | 1.87 | 4 | 51.31 |
| 2 | tusz (held-out half) | 557.15 | 1332 | 57.38 |
| 2 | mental_arith | 1.87 | 2 | 25.66 |
| 3 | tusz (held-out half) | 557.15 | 1134 | 48.85 |
| 3 | mental_arith | 1.87 | 1 | 12.83 |
| 4 | tusz (held-out half) | 557.15 | 1406 | 60.57 |
| 4 | mental_arith | 1.87 | 2 | 25.66 |

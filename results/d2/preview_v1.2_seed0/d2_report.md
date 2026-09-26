# D2: experiments 1-4 and alarm logic

Generated 2026-09-26T14:43:20 · commit 7388fde · Python 3.13.2 · seeds [0] · steps ['normalize', 'context', 'clock', 'tusz'] · feature version d1-v1-284c11e880 · 106 min

Method: docs/evaluation_methods.md v1.2. Every choice was made per fold on inner validation patients; no test result was used.

## Results

| Test | Result |
|---|---|
| VT-15 improvement over D1 | FAIL: mean per-patient AUROC 0.600 ± 0.000 (95% CI 0.527–0.678) vs D1 0.553 on the same seeds: +8.6% (target +15%). Wilcoxon p = 0.191. Nice to have (≥ 0.75): not met |
| VT-17 event-level performance | FAIL: sensitivity 0.10 (target ≥ 0.80), 5.09 false alarms per 24 h (target ≤ 5), largest p vs chance 0.565 |
| Reference: clock-only model | mean AUROC 0.697 |
| D2 without time-of-day features | mean AUROC 0.505 |
| Note | Only seeds [0] were run; the plan requires all five |

## Setups chosen (per test patient fold)

| Setup | Folds |
|---|---|
| norm=on ctx=10min clock=on tusz=off | 5 |
| norm=off ctx=0min clock=on tusz=off | 5 |
| norm=off ctx=10min clock=on tusz=on | 4 |
| norm=off ctx=5min clock=on tusz=off | 3 |
| norm=off ctx=2min clock=off tusz=off | 2 |
| norm=on ctx=10min clock=on tusz=on | 2 |
| norm=off ctx=5min clock=off tusz=on | 1 |
| norm=off ctx=2min clock=on tusz=off | 1 |
| norm=off ctx=5min clock=off tusz=off | 1 |
| norm=on ctx=5min clock=on tusz=off | 1 |

Setup chosen on all patients (used for the false-alarm sets): norm=on ctx=0min clock=on tusz=off, alarm smoothing 36, persistence 1.
Dataset check: a model can tell TUSZ from CHB-MIT/Siena interictal windows with AUROC 0.811 (0.5 = indistinguishable).

## Per seed

| Seed | AUROC | Without clock | Clock only | Sensitivity | FAR / 24 h | Time in warning | Chance prob. | p |
|---|---|---|---|---|---|---|---|---|
| 0 | 0.600 | 0.505 | 0.697 | 11/111 (0.10) | 5.09 | 0.101 | 0.100 | 0.565 |

## Per test patient (mean over seeds)

| Patient | D1 AUROC | D2 AUROC | Clock only | Sensitivity | FAR / 24 h |
|---|---|---|---|---|---|
| chbmit:chb08 | 0.420 | 0.110 | 0.199 | 0.00 | 9.82 |
| chbmit:chb04 | 0.313 | 0.235 | 0.347 | 0.25 | 3.59 |
| chbmit:chb09 | 0.279 | 0.324 | 0.593 | 0.00 | 12.43 |
| chbmit:chb20 | 0.827 | 0.402 | 0.549 | 0.00 | 2.90 |
| chbmit:chb14 | 0.458 | 0.406 | 0.457 | 0.00 | 0.00 |
| chbmit:chb01 | 0.519 | 0.475 | 0.823 | 0.00 | 3.54 |
| chbmit:chb22 | 0.649 | 0.516 | 0.344 | 0.00 | 1.61 |
| chbmit:chb06 | 0.447 | 0.516 | 0.675 | 0.00 | 2.34 |
| chbmit:chb16 | 0.428 | 0.529 | 0.565 | 0.00 | 0.00 |
| chbmit:chb19 | 0.518 | 0.539 | 0.840 | 0.00 | 0.00 |
| chbmit:chb03 | 0.484 | 0.585 | 0.574 | 0.17 | 2.77 |
| chbmit:chb10 | 0.615 | 0.609 | 0.775 | 0.00 | 1.54 |
| chbmit:chb17 | 0.651 | 0.610 | 0.711 | 0.33 | 6.22 |
| siena:PN03 | 0.657 | 0.613 | 1.000 | 1.00 | 43.54 |
| chbmit:chb05 | 0.548 | 0.617 | 0.801 | 0.40 | 8.64 |
| chbmit:chb02 | 0.340 | 0.677 | 1.000 | 0.00 | 5.65 |
| chbmit:chb13 | 0.672 | 0.698 | 0.456 | 0.20 | 5.57 |
| chbmit:chb15 | 0.423 | 0.731 | 0.557 | 0.00 | 0.69 |
| chbmit:chb18 | 0.654 | 0.757 | 0.927 | 0.25 | 1.44 |
| chbmit:chb23 | 0.727 | 0.803 | 0.926 | 0.20 | 4.01 |
| siena:PN07 | 0.419 | 0.822 | 1.000 | 0.00 | 5.85 |
| siena:PN14 | 0.760 | 0.840 | 0.791 | 0.25 | 7.83 |
| siena:PN01 | 0.943 | 0.856 | 0.802 | 0.00 | 5.78 |
| chbmit:chb07 | 0.545 | 0.860 | 0.950 | 0.00 | 4.78 |
| chbmit:chb11 | 0.518 | 0.870 | 0.749 | 0.00 | 1.42 |

## False-alarm sets (setup chosen on all patients)

| Seed | Set | Hours | False alarms | FAR / 24 h |
|---|---|---|---|---|
| 0 | tusz (held-out half) | 557.15 | 0 | 0.00 |
| 0 | mental_arith | 1.87 | 0 | 0.00 |

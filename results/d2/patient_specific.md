# Patient-specific test (characterization)

Generated 2026-09-26T15:26:55 · seeds [0, 1, 2, 3, 4] · D1 model and features, leave one seizure out within each patient (docs/evaluation_methods.md v1.3, Section 11).

| Result | Value |
|---|---|
| Patients | 22 |
| Mean patient-specific AUROC | 0.662 (95% CI 0.588–0.742) |
| Patient-specific clock-only AUROC | 0.600 |
| Patients where the EEG model beats their clock-only model | 13 of 22 |
| Same patients, cross-patient D1 AUROC | 0.568 |
| Same patients, cross-patient D2 AUROC | nan |

| Patient | Dataset | Seizures | Patient-specific | Clock only | Cross-patient D1 | Cross-patient D2 |
|---|---|---|---|---|---|---|
| siena:PN01 | siena | 2 | 1.000 | 0.003 | 0.970 | nan |
| chbmit:chb23 | chbmit | 5 | 0.928 | 0.369 | 0.782 | nan |
| chbmit:chb20 | chbmit | 5 | 0.915 | 0.813 | 0.723 | nan |
| siena:PN14 | siena | 4 | 0.910 | 1.000 | 0.751 | nan |
| chbmit:chb17 | chbmit | 3 | 0.843 | 0.148 | 0.666 | nan |
| chbmit:chb05 | chbmit | 5 | 0.823 | 0.664 | 0.574 | nan |
| chbmit:chb16 | chbmit | 5 | 0.746 | 1.000 | 0.426 | nan |
| chbmit:chb13 | chbmit | 5 | 0.745 | 0.471 | 0.629 | nan |
| chbmit:chb19 | chbmit | 2 | 0.735 | 0.861 | 0.532 | nan |
| chbmit:chb10 | chbmit | 6 | 0.675 | 0.547 | 0.635 | nan |
| chbmit:chb06 | chbmit | 10 | 0.612 | 0.438 | 0.430 | nan |
| chbmit:chb01 | chbmit | 10 | 0.610 | 0.693 | 0.484 | nan |
| chbmit:chb15 | chbmit | 9 | 0.598 | 0.348 | 0.503 | nan |
| chbmit:chb07 | chbmit | 3 | 0.597 | 0.870 | 0.545 | nan |
| chbmit:chb14 | chbmit | 6 | 0.596 | 0.553 | 0.474 | nan |
| chbmit:chb04 | chbmit | 4 | 0.589 | 0.339 | 0.367 | nan |
| chbmit:chb03 | chbmit | 6 | 0.578 | 0.020 | 0.493 | nan |
| chbmit:chb09 | chbmit | 4 | 0.499 | 0.364 | 0.344 | nan |
| chbmit:chb18 | chbmit | 4 | 0.481 | 0.727 | 0.560 | nan |
| chbmit:chb02 | chbmit | 2 | 0.462 | 0.973 | 0.372 | nan |
| chbmit:chb22 | chbmit | 2 | 0.344 | 1.000 | 0.649 | nan |
| siena:PN03 | siena | 2 | 0.279 | 1.000 | 0.592 | nan |

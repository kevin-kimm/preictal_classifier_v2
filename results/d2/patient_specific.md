# Patient-specific test (characterization)

Generated 2026-09-27T10:31:41 · seeds [0, 1, 2, 3, 4] · D1 model and features, leave one seizure out within each patient (docs/evaluation_methods.md v1.3, Section 11).

| Result | Value |
|---|---|
| Patients | 22 |
| Mean patient-specific AUROC | 0.662 (95% CI 0.588–0.742) |
| Patient-specific clock-only AUROC | 0.600 |
| Patients where the EEG model beats their clock-only model | 13 of 22 |
| Same patients, cross-patient D1 AUROC | 0.568 |
| Same patients, cross-patient D2 AUROC | 0.616 |

| Patient | Dataset | Seizures | Patient-specific | Clock only | Cross-patient D1 | Cross-patient D2 |
|---|---|---|---|---|---|---|
| siena:PN01 | siena | 2 | 1.000 | 0.003 | 0.970 | 0.997 |
| chbmit:chb23 | chbmit | 5 | 0.928 | 0.369 | 0.782 | 0.857 |
| chbmit:chb20 | chbmit | 5 | 0.915 | 0.813 | 0.723 | 0.385 |
| siena:PN14 | siena | 4 | 0.910 | 1.000 | 0.751 | 0.767 |
| chbmit:chb17 | chbmit | 3 | 0.843 | 0.148 | 0.666 | 0.631 |
| chbmit:chb05 | chbmit | 5 | 0.823 | 0.664 | 0.574 | 0.641 |
| chbmit:chb16 | chbmit | 5 | 0.746 | 1.000 | 0.426 | 0.428 |
| chbmit:chb13 | chbmit | 5 | 0.745 | 0.471 | 0.629 | 0.467 |
| chbmit:chb19 | chbmit | 2 | 0.735 | 0.861 | 0.532 | 0.671 |
| chbmit:chb10 | chbmit | 6 | 0.675 | 0.547 | 0.635 | 0.655 |
| chbmit:chb06 | chbmit | 10 | 0.612 | 0.438 | 0.430 | 0.487 |
| chbmit:chb01 | chbmit | 10 | 0.610 | 0.693 | 0.484 | 0.600 |
| chbmit:chb15 | chbmit | 9 | 0.598 | 0.348 | 0.503 | 0.703 |
| chbmit:chb07 | chbmit | 3 | 0.597 | 0.870 | 0.545 | 0.902 |
| chbmit:chb14 | chbmit | 6 | 0.596 | 0.553 | 0.474 | 0.376 |
| chbmit:chb04 | chbmit | 4 | 0.589 | 0.339 | 0.367 | 0.316 |
| chbmit:chb03 | chbmit | 6 | 0.578 | 0.020 | 0.493 | 0.442 |
| chbmit:chb09 | chbmit | 4 | 0.499 | 0.364 | 0.344 | 0.349 |
| chbmit:chb18 | chbmit | 4 | 0.481 | 0.727 | 0.560 | 0.804 |
| chbmit:chb02 | chbmit | 2 | 0.462 | 0.973 | 0.372 | 0.715 |
| chbmit:chb22 | chbmit | 2 | 0.344 | 1.000 | 0.649 | 0.517 |
| siena:PN03 | siena | 2 | 0.279 | 1.000 | 0.592 | 0.830 |

# D1 diagnostics (not a verification test)

Generated 2026-09-26T11:17:21 · seed 0 · same folds and model as the D1 run. Nothing here changes the D1 model.

## Summary (mean over test patients)

| Check | Value |
|---|---|
| Preictal vs interictal, EEG model (AUROC) | 0.553 |
| Preictal vs interictal, clock time only (AUROC) | 0.697 |
| Seizure detection, all ictal windows (AUROC of ictal probability) | 0.810 (pooled 0.710) |
| Seizure detection, windows entirely inside a seizure | 0.865 (pooled 0.719) |
| Median preictal risk on interictal windows, across patients | min 0.015, median 0.269, max 0.947 |

## Per test patient

| Patient | EEG AUROC | Clock AUROC | Seizure detection (all / inside) | Ictal windows (inside) | Median risk: interictal / preictal |
|---|---|---|---|---|---|
| chbmit:chb09 | 0.279 | 0.593 | 0.944 / 0.999 | 56 (32) | 0.371 / 0.126 |
| chbmit:chb04 | 0.313 | 0.347 | 0.886 / 0.959 | 76 (52) | 0.335 / 0.138 |
| chbmit:chb02 | 0.340 | 1.000 | 0.961 / 0.995 | 35 (21) | 0.336 / 0.168 |
| siena:PN07 | 0.419 | 1.000 | 0.962 / 1.000 | 13 (7) | 0.653 / 0.593 |
| chbmit:chb08 | 0.420 | 0.199 | 0.503 / 0.427 | 185 (155) | 0.486 / 0.410 |
| chbmit:chb15 | 0.423 | 0.557 | 0.517 / 0.529 | 402 (282) | 0.140 / 0.107 |
| chbmit:chb16 | 0.428 | 0.565 | 0.493 / nan | 21 (0) | 0.347 / 0.285 |
| chbmit:chb06 | 0.447 | 0.675 | 0.722 / nan | 33 (0) | 0.043 / 0.022 |
| chbmit:chb14 | 0.458 | 0.457 | 0.776 / 0.579 | 34 (2) | 0.164 / 0.129 |
| chbmit:chb03 | 0.484 | 0.574 | 0.830 / 0.913 | 80 (38) | 0.342 / 0.318 |
| chbmit:chb11 | 0.518 | 0.749 | 0.978 / 0.976 | 163 (146) | 0.269 / 0.282 |
| chbmit:chb19 | 0.518 | 0.840 | 0.961 / 1.000 | 49 (31) | 0.222 / 0.239 |
| chbmit:chb01 | 0.519 | 0.823 | 0.679 / 0.664 | 130 (68) | 0.383 / 0.396 |
| chbmit:chb07 | 0.545 | 0.950 | 0.961 / 0.965 | 67 (49) | 0.285 / 0.312 |
| chbmit:chb05 | 0.548 | 0.801 | 0.914 / 0.979 | 112 (82) | 0.240 / 0.287 |
| chbmit:chb10 | 0.615 | 0.775 | 0.916 / 0.977 | 89 (47) | 0.015 / 0.030 |
| chbmit:chb22 | 0.649 | 0.344 | 0.966 / 0.999 | 42 (24) | 0.186 / 0.451 |
| chbmit:chb17 | 0.651 | 0.711 | 0.854 / 0.835 | 59 (41) | 0.071 / 0.176 |
| chbmit:chb18 | 0.654 | 0.927 | 0.861 / 0.980 | 63 (27) | 0.074 / 0.171 |
| siena:PN03 | 0.657 | 1.000 | 0.901 / 0.983 | 48 (36) | 0.947 / 0.982 |
| chbmit:chb13 | 0.672 | 0.456 | 0.382 / 0.351 | 109 (45) | 0.242 / 0.405 |
| chbmit:chb23 | 0.727 | 0.926 | 0.877 / 0.846 | 89 (48) | 0.208 / 0.325 |
| siena:PN14 | 0.760 | 0.791 | 0.868 / 0.997 | 34 (14) | 0.075 / 0.831 |
| chbmit:chb20 | 0.827 | 0.549 | 0.699 / 0.942 | 61 (13) | 0.286 / 0.645 |
| siena:PN01 | 0.943 | 0.802 | 0.835 / 0.990 | 26 (14) | 0.683 / 0.966 |

# Personalized models (characterization)

Generated 2026-09-28T19:32:52 · seeds [0, 1, 2, 3, 4] · 22 patients · docs/evaluation_methods.md v1.4, Section 11.1 (and v1.6, Section 11.3). Every variant is scored on the same test windows.

| Model | Mean AUROC | 95% CI | Beats the patient's clock-only model | p (vs clock only) |
|---|---|---|---|---|
| This patient only, EEG (patient-specific test) | 0.662 | 0.588–0.742 | 13 of 22 | 0.463 |
| This patient only, clock only (patient-specific test) | 0.600 | 0.475–0.730 | – | nan |
| Other patients only, EEG + time of day (feature set v1, no baseline) | 0.642 | 0.552–0.728 | 11 of 22 | 1 |
| Other patients + this patient, EEG + time of day (feature set v1, no baseline) | 0.698 | 0.606–0.789 | 12 of 22 | 0.483 |
| Other patients only, EEG + time of day (feature set v2) | 0.643 | 0.559–0.724 | 11 of 22 | 0.924 |
| Other patients + this patient, EEG + time of day (feature set v2) | 0.696 | 0.605–0.785 | 11 of 22 | 0.463 |

## Paired comparisons (per patient, mean over seeds)

| Comparison | Patients where the first is higher | Wilcoxon p |
|---|---|---|
| Other patients + this patient, EEG + time of day (feature set v2) vs Other patients only, EEG + time of day (feature set v2) | 15 of 22 | 0.0634 |
| Other patients + this patient, EEG + time of day (feature set v2) vs This patient only, EEG (patient-specific test) | 11 of 22 | 0.899 |
| Other patients only, EEG + time of day (feature set v2) vs Other patients only, EEG + time of day (feature set v1, no baseline) | 10 of 22 | 0.849 |
| Other patients + this patient, EEG + time of day (feature set v2) vs Other patients + this patient, EEG + time of day (feature set v1, no baseline) | 13 of 22 | 0.975 |

## Per patient (mean over seeds)

| Patient | Seizures | This patient only, EEG (patient-specific test) | This patient only, clock only (patient-specific test) | Other patients only, EEG + time of day (feature set v1, no baseline) | Other patients + this patient, EEG + time of day (feature set v1, no baseline) | Other patients only, EEG + time of day (feature set v2) | Other patients + this patient, EEG + time of day (feature set v2) |
|---|---|---|---|---|---|---|---|
| siena:PN01 | 2 | 1.000 | 0.003 | 0.999 | 1.000 | 0.999 | 1.000 |
| siena:PN03 | 2 | 0.279 | 1.000 | 0.908 | 0.992 | 0.795 | 0.993 |
| chbmit:chb15 | 9 | 0.598 | 0.348 | 0.740 | 0.991 | 0.777 | 0.989 |
| chbmit:chb20 | 5 | 0.915 | 0.813 | 0.749 | 0.890 | 0.772 | 0.916 |
| siena:PN14 | 4 | 0.910 | 1.000 | 0.793 | 0.915 | 0.790 | 0.916 |
| chbmit:chb07 | 3 | 0.597 | 0.870 | 0.924 | 0.907 | 0.909 | 0.913 |
| chbmit:chb13 | 5 | 0.745 | 0.471 | 0.678 | 0.858 | 0.631 | 0.844 |
| chbmit:chb17 | 3 | 0.843 | 0.148 | 0.831 | 0.805 | 0.800 | 0.798 |
| chbmit:chb05 | 5 | 0.823 | 0.664 | 0.664 | 0.784 | 0.713 | 0.771 |
| chbmit:chb23 | 5 | 0.928 | 0.369 | 0.860 | 0.783 | 0.873 | 0.744 |
| chbmit:chb16 | 5 | 0.746 | 1.000 | 0.502 | 0.721 | 0.529 | 0.731 |
| chbmit:chb19 | 2 | 0.735 | 0.861 | 0.667 | 0.787 | 0.733 | 0.712 |
| chbmit:chb01 | 10 | 0.610 | 0.693 | 0.611 | 0.700 | 0.593 | 0.692 |
| chbmit:chb18 | 4 | 0.481 | 0.727 | 0.749 | 0.622 | 0.744 | 0.630 |
| chbmit:chb02 | 2 | 0.462 | 0.973 | 0.412 | 0.555 | 0.471 | 0.566 |
| chbmit:chb10 | 6 | 0.675 | 0.547 | 0.695 | 0.549 | 0.681 | 0.561 |
| chbmit:chb14 | 6 | 0.596 | 0.553 | 0.249 | 0.538 | 0.262 | 0.551 |
| chbmit:chb03 | 6 | 0.578 | 0.020 | 0.535 | 0.510 | 0.510 | 0.536 |
| chbmit:chb22 | 2 | 0.344 | 1.000 | 0.463 | 0.389 | 0.450 | 0.443 |
| chbmit:chb09 | 4 | 0.499 | 0.364 | 0.333 | 0.409 | 0.322 | 0.372 |
| chbmit:chb06 | 10 | 0.612 | 0.438 | 0.494 | 0.349 | 0.525 | 0.354 |
| chbmit:chb04 | 4 | 0.589 | 0.339 | 0.271 | 0.302 | 0.265 | 0.285 |

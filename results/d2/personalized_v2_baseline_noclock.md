# Personalized models (characterization)

Generated 2026-09-28T22:59:41 · seeds [0, 1, 2, 3, 4] · 22 patients · docs/evaluation_methods.md v1.4, Section 11.1 (and v1.6, Section 11.3). Every variant is scored on the same test windows.

| Model | Mean AUROC | 95% CI | Beats the patient's clock-only model | p (vs clock only) |
|---|---|---|---|---|
| This patient only, EEG (patient-specific test) | 0.662 | 0.588–0.742 | 13 of 22 | 0.463 |
| This patient only, clock only (patient-specific test) | 0.600 | 0.475–0.730 | – | nan |
| Other patients only, EEG + time of day (feature set v1, no baseline) | 0.642 | 0.552–0.728 | 11 of 22 | 1 |
| Other patients + this patient, EEG + time of day (feature set v1, no baseline) | 0.698 | 0.606–0.789 | 12 of 22 | 0.483 |
| Other patients only, EEG (feature set v2, personal baseline, no time of day) | 0.529 | 0.457–0.599 | 11 of 22 | 0.424 |
| Other patients + this patient, EEG (feature set v2, personal baseline, no time of day) | 0.681 | 0.620–0.744 | 13 of 22 | 0.388 |

## Paired comparisons (per patient, mean over seeds)

| Comparison | Patients where the first is higher | Wilcoxon p |
|---|---|---|
| Other patients + this patient, EEG (feature set v2, personal baseline, no time of day) vs Other patients only, EEG (feature set v2, personal baseline, no time of day) | 19 of 22 | 0.00145 |
| Other patients + this patient, EEG (feature set v2, personal baseline, no time of day) vs This patient only, EEG (patient-specific test) | 11 of 22 | 0.588 |
| Other patients only, EEG (feature set v2, personal baseline, no time of day) vs Other patients only, EEG + time of day (feature set v1, no baseline) | 8 of 22 | 0.0684 |
| Other patients + this patient, EEG (feature set v2, personal baseline, no time of day) vs Other patients + this patient, EEG + time of day (feature set v1, no baseline) | 11 of 22 | 0.799 |

## Per patient (mean over seeds)

| Patient | Seizures | This patient only, EEG (patient-specific test) | This patient only, clock only (patient-specific test) | Other patients only, EEG + time of day (feature set v1, no baseline) | Other patients + this patient, EEG + time of day (feature set v1, no baseline) | Other patients only, EEG (feature set v2, personal baseline, no time of day) | Other patients + this patient, EEG (feature set v2, personal baseline, no time of day) |
|---|---|---|---|---|---|---|---|
| siena:PN01 | 2 | 1.000 | 0.003 | 0.999 | 1.000 | 0.694 | 0.991 |
| chbmit:chb23 | 5 | 0.928 | 0.369 | 0.860 | 0.783 | 0.742 | 0.911 |
| chbmit:chb19 | 2 | 0.735 | 0.861 | 0.667 | 0.787 | 0.280 | 0.903 |
| chbmit:chb13 | 5 | 0.745 | 0.471 | 0.678 | 0.858 | 0.299 | 0.859 |
| siena:PN14 | 4 | 0.910 | 1.000 | 0.793 | 0.915 | 0.758 | 0.828 |
| chbmit:chb17 | 3 | 0.843 | 0.148 | 0.831 | 0.805 | 0.842 | 0.824 |
| chbmit:chb20 | 5 | 0.915 | 0.813 | 0.749 | 0.890 | 0.214 | 0.796 |
| chbmit:chb05 | 5 | 0.823 | 0.664 | 0.664 | 0.784 | 0.717 | 0.754 |
| chbmit:chb10 | 6 | 0.675 | 0.547 | 0.695 | 0.549 | 0.577 | 0.709 |
| chbmit:chb01 | 10 | 0.610 | 0.693 | 0.611 | 0.700 | 0.397 | 0.676 |
| chbmit:chb16 | 5 | 0.746 | 1.000 | 0.502 | 0.721 | 0.435 | 0.675 |
| chbmit:chb07 | 3 | 0.597 | 0.870 | 0.924 | 0.907 | 0.342 | 0.640 |
| chbmit:chb14 | 6 | 0.596 | 0.553 | 0.249 | 0.538 | 0.619 | 0.632 |
| chbmit:chb06 | 10 | 0.612 | 0.438 | 0.494 | 0.349 | 0.550 | 0.602 |
| chbmit:chb22 | 2 | 0.344 | 1.000 | 0.463 | 0.389 | 0.762 | 0.577 |
| chbmit:chb18 | 4 | 0.481 | 0.727 | 0.749 | 0.622 | 0.463 | 0.564 |
| chbmit:chb03 | 6 | 0.578 | 0.020 | 0.535 | 0.510 | 0.438 | 0.561 |
| chbmit:chb09 | 4 | 0.499 | 0.364 | 0.333 | 0.409 | 0.540 | 0.541 |
| chbmit:chb15 | 9 | 0.598 | 0.348 | 0.740 | 0.991 | 0.517 | 0.533 |
| siena:PN03 | 2 | 0.279 | 1.000 | 0.908 | 0.992 | 0.398 | 0.476 |
| chbmit:chb02 | 2 | 0.462 | 0.973 | 0.412 | 0.555 | 0.705 | 0.474 |
| chbmit:chb04 | 4 | 0.589 | 0.339 | 0.271 | 0.302 | 0.349 | 0.448 |

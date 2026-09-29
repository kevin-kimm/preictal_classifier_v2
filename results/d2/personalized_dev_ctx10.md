# Personalized models (characterization)

Generated 2026-09-29T03:30:19 · seeds [0, 1, 2, 3, 4] · 22 patients · docs/evaluation_methods.md v1.4, Section 11.1 (and v1.6, Section 11.3). Every variant is scored on the same test windows.

| Model | Mean AUROC | 95% CI | Beats the patient's clock-only model | p (vs clock only) |
|---|---|---|---|---|
| This patient only, EEG (patient-specific test) | 0.662 | 0.588–0.742 | 13 of 22 | 0.463 |
| This patient only, clock only (patient-specific test) | 0.600 | 0.475–0.730 | – | nan |
| Other patients + this patient (feature set v1 with time of day, no baseline) | 0.681 | 0.620–0.744 | 13 of 22 | 0.388 |
| Other patients + this patient, EEG (feature set v2, personal baseline, no time of day, 10 min context) | 0.700 | 0.630–0.768 | 13 of 22 | 0.371 |

## Paired comparisons (per patient, mean over seeds)

| Comparison | Patients where the first is higher | Wilcoxon p |
|---|---|---|
| Other patients + this patient, EEG (feature set v2, personal baseline, no time of day, 10 min context) vs This patient only, EEG (patient-specific test) | 11 of 22 | 0.388 |
| Other patients + this patient, EEG (feature set v2, personal baseline, no time of day, 10 min context) vs Other patients + this patient (feature set v1 with time of day, no baseline) | 11 of 22 | 0.799 |

## Per patient (mean over seeds)

| Patient | Seizures | This patient only, EEG (patient-specific test) | This patient only, clock only (patient-specific test) | Other patients + this patient (feature set v1 with time of day, no baseline) | Other patients + this patient, EEG (feature set v2, personal baseline, no time of day, 10 min context) |
|---|---|---|---|---|---|
| siena:PN01 | 2 | 1.000 | 0.003 | 0.991 | 0.988 |
| siena:PN14 | 4 | 0.910 | 1.000 | 0.828 | 0.951 |
| chbmit:chb19 | 2 | 0.735 | 0.861 | 0.903 | 0.914 |
| chbmit:chb23 | 5 | 0.928 | 0.369 | 0.911 | 0.910 |
| chbmit:chb13 | 5 | 0.745 | 0.471 | 0.859 | 0.874 |
| siena:PN03 | 2 | 0.279 | 1.000 | 0.476 | 0.872 |
| chbmit:chb17 | 3 | 0.843 | 0.148 | 0.824 | 0.827 |
| chbmit:chb20 | 5 | 0.915 | 0.813 | 0.796 | 0.744 |
| chbmit:chb05 | 5 | 0.823 | 0.664 | 0.754 | 0.730 |
| chbmit:chb03 | 6 | 0.578 | 0.020 | 0.561 | 0.702 |
| chbmit:chb16 | 5 | 0.746 | 1.000 | 0.675 | 0.698 |
| chbmit:chb10 | 6 | 0.675 | 0.547 | 0.709 | 0.687 |
| chbmit:chb14 | 6 | 0.596 | 0.553 | 0.632 | 0.683 |
| chbmit:chb06 | 10 | 0.612 | 0.438 | 0.602 | 0.675 |
| chbmit:chb07 | 3 | 0.597 | 0.870 | 0.640 | 0.627 |
| chbmit:chb01 | 10 | 0.610 | 0.693 | 0.676 | 0.599 |
| chbmit:chb15 | 9 | 0.598 | 0.348 | 0.533 | 0.554 |
| chbmit:chb02 | 2 | 0.462 | 0.973 | 0.474 | 0.553 |
| chbmit:chb09 | 4 | 0.499 | 0.364 | 0.541 | 0.488 |
| chbmit:chb18 | 4 | 0.481 | 0.727 | 0.564 | 0.475 |
| chbmit:chb22 | 2 | 0.344 | 1.000 | 0.577 | 0.454 |
| chbmit:chb04 | 4 | 0.589 | 0.339 | 0.448 | 0.405 |

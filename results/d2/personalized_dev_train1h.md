# Personalized models (characterization)

Generated 2026-09-29T12:31:19 · seeds [0, 1, 2, 3, 4] · 22 patients · docs/evaluation_methods.md v1.4, Section 11.1 (and v1.6, Section 11.3). Every variant is scored on the same test windows.

| Model | Mean AUROC | 95% CI | Beats the patient's clock-only model | p (vs clock only) |
|---|---|---|---|---|
| This patient only, EEG (patient-specific test) | 0.662 | 0.588–0.742 | 13 of 22 | 0.463 |
| This patient only, clock only (patient-specific test) | 0.600 | 0.475–0.730 | – | nan |
| Other patients + this patient (base design) | 0.681 | 0.620–0.744 | 13 of 22 | 0.388 |
| Other patients + this patient, EEG (feature set v2, personal baseline, no time of day, trained with a 1 h gap) | 0.684 | 0.620–0.744 | 13 of 22 | 0.463 |

## Paired comparisons (per patient, mean over seeds)

| Comparison | Patients where the first is higher | Wilcoxon p |
|---|---|---|
| Other patients + this patient, EEG (feature set v2, personal baseline, no time of day, trained with a 1 h gap) vs This patient only, EEG (patient-specific test) | 12 of 22 | 0.702 |
| Other patients + this patient, EEG (feature set v2, personal baseline, no time of day, trained with a 1 h gap) vs Other patients + this patient (base design) | 11 of 22 | 0.726 |

## Per patient (mean over seeds)

| Patient | Seizures | This patient only, EEG (patient-specific test) | This patient only, clock only (patient-specific test) | Other patients + this patient (base design) | Other patients + this patient, EEG (feature set v2, personal baseline, no time of day, trained with a 1 h gap) |
|---|---|---|---|---|---|
| siena:PN01 | 2 | 1.000 | 0.003 | 0.991 | 0.944 |
| chbmit:chb23 | 5 | 0.928 | 0.369 | 0.911 | 0.930 |
| chbmit:chb19 | 2 | 0.735 | 0.861 | 0.903 | 0.858 |
| chbmit:chb17 | 3 | 0.843 | 0.148 | 0.824 | 0.838 |
| chbmit:chb20 | 5 | 0.915 | 0.813 | 0.796 | 0.828 |
| siena:PN03 | 2 | 0.279 | 1.000 | 0.476 | 0.794 |
| chbmit:chb13 | 5 | 0.745 | 0.471 | 0.859 | 0.778 |
| chbmit:chb16 | 5 | 0.746 | 1.000 | 0.675 | 0.749 |
| chbmit:chb10 | 6 | 0.675 | 0.547 | 0.709 | 0.735 |
| chbmit:chb07 | 3 | 0.597 | 0.870 | 0.640 | 0.706 |
| chbmit:chb05 | 5 | 0.823 | 0.664 | 0.754 | 0.705 |
| siena:PN14 | 4 | 0.910 | 1.000 | 0.828 | 0.685 |
| chbmit:chb02 | 2 | 0.462 | 0.973 | 0.474 | 0.683 |
| chbmit:chb01 | 10 | 0.610 | 0.693 | 0.676 | 0.633 |
| chbmit:chb06 | 10 | 0.612 | 0.438 | 0.602 | 0.594 |
| chbmit:chb14 | 6 | 0.596 | 0.553 | 0.632 | 0.587 |
| chbmit:chb03 | 6 | 0.578 | 0.020 | 0.561 | 0.569 |
| chbmit:chb09 | 4 | 0.499 | 0.364 | 0.541 | 0.567 |
| chbmit:chb18 | 4 | 0.481 | 0.727 | 0.564 | 0.558 |
| chbmit:chb04 | 4 | 0.589 | 0.339 | 0.448 | 0.460 |
| chbmit:chb22 | 2 | 0.344 | 1.000 | 0.577 | 0.440 |
| chbmit:chb15 | 9 | 0.598 | 0.348 | 0.533 | 0.413 |

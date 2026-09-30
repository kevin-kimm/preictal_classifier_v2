# Personalized models (characterization)

Generated 2026-09-30T07:26:09 · seeds [0, 1, 2, 3, 4] · 33 patients · docs/evaluation_methods.md v1.4, Section 11.1 (and v1.6, Section 11.3). Every variant is scored on the same test windows.

| Model | Mean AUROC | 95% CI | Beats the patient's clock-only model | p (vs clock only) |
|---|---|---|---|---|
| This patient only, EEG (patient-specific test) | 0.662 | 0.588–0.742 | 13 of 22 | 0.463 |
| This patient only, clock only (patient-specific test) | 0.600 | 0.475–0.730 | – | nan |
| Other patients + this patient (frozen design, 4 h gap) | 0.700 | 0.630–0.768 | 13 of 22 | 0.371 |
| Other patients + this patient, EEG (feature set v2, personal baseline, no time of day, 10 min context, 1 h gap for labels and testing) | 0.698 | 0.638–0.756 | 13 of 22 | 0.566 |

## Paired comparisons (per patient, mean over seeds)

| Comparison | Patients where the first is higher | Wilcoxon p |
|---|---|---|
| Other patients + this patient, EEG (feature set v2, personal baseline, no time of day, 10 min context, 1 h gap for labels and testing) vs This patient only, EEG (patient-specific test) | 13 of 22 | 0.824 |
| Other patients + this patient, EEG (feature set v2, personal baseline, no time of day, 10 min context, 1 h gap for labels and testing) vs Other patients + this patient (frozen design, 4 h gap) | 11 of 22 | 0.248 |

## Per patient (mean over seeds)

| Patient | Seizures | This patient only, EEG (patient-specific test) | This patient only, clock only (patient-specific test) | Other patients + this patient (frozen design, 4 h gap) | Other patients + this patient, EEG (feature set v2, personal baseline, no time of day, 10 min context, 1 h gap for labels and testing) |
|---|---|---|---|---|---|
| chbmit:chb20 | 5 | 0.915 | 0.813 | 0.744 | 0.971 |
| chbmit:chb23 | 5 | 0.928 | 0.369 | 0.910 | 0.967 |
| siena:PN12 | 2 | nan | nan | nan | 0.955 |
| chbmit:chb19 | 2 | 0.735 | 0.861 | 0.914 | 0.935 |
| chbmit:chb24 | 12 | nan | nan | nan | 0.921 |
| siena:PN05 | 3 | nan | nan | nan | 0.895 |
| chbmit:chb12 | 8 | nan | nan | nan | 0.863 |
| siena:PN16 | 2 | nan | nan | nan | 0.818 |
| chbmit:chb16 | 5 | 0.746 | 1.000 | 0.698 | 0.783 |
| siena:PN01 | 2 | 1.000 | 0.003 | 0.988 | 0.776 |
| chbmit:chb10 | 6 | 0.675 | 0.547 | 0.687 | 0.774 |
| chbmit:chb08 | 5 | nan | nan | nan | 0.767 |
| siena:PN14 | 4 | 0.910 | 1.000 | 0.951 | 0.761 |
| siena:PN13 | 3 | nan | nan | nan | 0.760 |
| chbmit:chb03 | 6 | 0.578 | 0.020 | 0.702 | 0.749 |
| siena:PN09 | 3 | nan | nan | nan | 0.714 |
| chbmit:chb17 | 3 | 0.843 | 0.148 | 0.827 | 0.714 |
| siena:PN06 | 5 | nan | nan | nan | 0.713 |
| chbmit:chb13 | 5 | 0.745 | 0.471 | 0.874 | 0.691 |
| chbmit:chb01 | 10 | 0.610 | 0.693 | 0.599 | 0.684 |
| siena:PN10 | 10 | nan | nan | nan | 0.670 |
| chbmit:chb07 | 3 | 0.597 | 0.870 | 0.627 | 0.665 |
| siena:PN17 | 2 | nan | nan | nan | 0.663 |
| chbmit:chb14 | 6 | 0.596 | 0.553 | 0.683 | 0.638 |
| chbmit:chb18 | 4 | 0.481 | 0.727 | 0.475 | 0.627 |
| chbmit:chb09 | 4 | 0.499 | 0.364 | 0.488 | 0.571 |
| chbmit:chb06 | 10 | 0.612 | 0.438 | 0.675 | 0.531 |
| chbmit:chb05 | 5 | 0.823 | 0.664 | 0.730 | 0.487 |
| chbmit:chb02 | 2 | 0.462 | 0.973 | 0.553 | 0.482 |
| chbmit:chb04 | 4 | 0.589 | 0.339 | 0.405 | 0.458 |
| siena:PN03 | 2 | 0.279 | 1.000 | 0.872 | 0.416 |
| chbmit:chb15 | 9 | 0.598 | 0.348 | 0.554 | 0.359 |
| chbmit:chb22 | 2 | 0.344 | 1.000 | 0.454 | 0.244 |

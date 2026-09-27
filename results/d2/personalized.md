# Personalized models (characterization)

Generated 2026-09-27T13:26:04 · seeds [0, 1, 2, 3, 4] · 22 patients · docs/evaluation_methods.md v1.4, Section 11.1. Every variant is scored on the same test windows.

| Model | Mean AUROC | 95% CI | Beats the patient's clock-only model | p (vs clock only) |
|---|---|---|---|---|
| This patient only, EEG (patient-specific test) | 0.662 | 0.588–0.742 | 13 of 22 | 0.463 |
| This patient only, clock only (patient-specific test) | 0.600 | 0.475–0.730 | – | nan |
| This patient only, EEG + time of day | 0.678 | 0.593–0.761 | 11 of 22 | 0.566 |
| This patient only, EEG + 10 min context + time of day | 0.688 | 0.592–0.782 | 14 of 22 | 0.198 |
| Other patients only, EEG + time of day | 0.642 | 0.552–0.728 | 11 of 22 | 1 |
| Other patients + this patient, EEG + time of day | 0.698 | 0.606–0.789 | 12 of 22 | 0.483 |

## Paired comparisons (per patient, mean over seeds)

| Comparison | Patients where the first is higher | Wilcoxon p |
|---|---|---|
| Other patients + this patient, EEG + time of day vs Other patients only, EEG + time of day | 14 of 22 | 0.0794 |
| Other patients + this patient, EEG + time of day vs This patient only, EEG (patient-specific test) | 11 of 22 | 0.799 |
| This patient only, EEG + time of day vs This patient only, EEG (patient-specific test) | 9 of 22 | 0.75 |
| This patient only, EEG + 10 min context + time of day vs This patient only, EEG + time of day | 17 of 22 | 0.0735 |

## Per patient (mean over seeds)

| Patient | Seizures | This patient only, EEG (patient-specific test) | This patient only, clock only (patient-specific test) | This patient only, EEG + time of day | This patient only, EEG + 10 min context + time of day | Other patients only, EEG + time of day | Other patients + this patient, EEG + time of day |
|---|---|---|---|---|---|---|---|
| siena:PN01 | 2 | 1.000 | 0.003 | 0.898 | 0.935 | 0.999 | 1.000 |
| siena:PN03 | 2 | 0.279 | 1.000 | 0.651 | 0.142 | 0.908 | 0.992 |
| chbmit:chb15 | 9 | 0.598 | 0.348 | 0.958 | 0.967 | 0.740 | 0.991 |
| siena:PN14 | 4 | 0.910 | 1.000 | 0.810 | 0.888 | 0.793 | 0.915 |
| chbmit:chb07 | 3 | 0.597 | 0.870 | 0.787 | 0.789 | 0.924 | 0.907 |
| chbmit:chb20 | 5 | 0.915 | 0.813 | 0.719 | 0.946 | 0.749 | 0.890 |
| chbmit:chb13 | 5 | 0.745 | 0.471 | 0.590 | 0.623 | 0.678 | 0.858 |
| chbmit:chb17 | 3 | 0.843 | 0.148 | 0.837 | 0.855 | 0.831 | 0.805 |
| chbmit:chb19 | 2 | 0.735 | 0.861 | 0.735 | 0.837 | 0.667 | 0.787 |
| chbmit:chb05 | 5 | 0.823 | 0.664 | 0.821 | 0.841 | 0.664 | 0.784 |
| chbmit:chb23 | 5 | 0.928 | 0.369 | 0.511 | 0.699 | 0.860 | 0.783 |
| chbmit:chb16 | 5 | 0.746 | 1.000 | 0.882 | 0.891 | 0.502 | 0.721 |
| chbmit:chb01 | 10 | 0.610 | 0.693 | 0.642 | 0.666 | 0.611 | 0.700 |
| chbmit:chb18 | 4 | 0.481 | 0.727 | 0.514 | 0.474 | 0.749 | 0.622 |
| chbmit:chb02 | 2 | 0.462 | 0.973 | 1.000 | 1.000 | 0.412 | 0.555 |
| chbmit:chb10 | 6 | 0.675 | 0.547 | 0.476 | 0.570 | 0.695 | 0.549 |
| chbmit:chb14 | 6 | 0.596 | 0.553 | 0.582 | 0.583 | 0.249 | 0.538 |
| chbmit:chb03 | 6 | 0.578 | 0.020 | 0.336 | 0.379 | 0.535 | 0.510 |
| chbmit:chb09 | 4 | 0.499 | 0.364 | 0.460 | 0.410 | 0.333 | 0.409 |
| chbmit:chb22 | 2 | 0.344 | 1.000 | 0.887 | 0.697 | 0.463 | 0.389 |
| chbmit:chb06 | 10 | 0.612 | 0.438 | 0.352 | 0.460 | 0.494 | 0.349 |
| chbmit:chb04 | 4 | 0.589 | 0.339 | 0.466 | 0.495 | 0.271 | 0.302 |

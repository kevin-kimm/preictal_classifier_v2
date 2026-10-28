# D2 improvement round: challengers to the frozen design (chbmit_siena)

Generated 2026-10-27T22:30:10 · docs/evaluation_methods.md v1.25, Section 14.2. Every arm is scored on the same test windows with the frozen labels. Adoption rule (Section 14.3): mean AUROC at least 0.01 above the frozen design on the pooled development patients, and higher in more than half of them.

| Arm | Patients | Seeds | Mean AUROC | 95% CI | Change vs frozen | Higher than frozen in | Wilcoxon p |
|---|---|---|---|---|---|---|---|
| Frozen design | 22 | 2 | 0.705 | 0.638–0.770 | – | – | – |
| Trained with a 10 min preictal period | 22 | 2 | 0.697 | 0.633–0.764 | -0.009 | 10 of 22 | 0.924 |
| Trained with a 20 min preictal period | 22 | 2 | 0.696 | 0.634–0.758 | -0.010 | 11 of 22 | 0.824 |
| Trained with a 45 min preictal period | 22 | 2 | 0.706 | 0.642–0.770 | +0.001 | 10 of 22 | 0.824 |
| Trained with a 60 min preictal period | 21 | 2 | 0.663 | 0.603–0.721 | -0.032 | 9 of 21 | 0.147 |
| Trained without windows that straddle two states | 22 | 2 | 0.688 | 0.610–0.761 | -0.017 | 6 of 22 | 0.176 |
| Plus per-channel features | 22 | 2 | 0.714 | 0.647–0.781 | +0.009 | 14 of 22 | 0.388 |
| Average of the frozen model and a patient-only model | 22 | 2 | 0.710 | 0.642–0.776 | +0.005 | 13 of 22 | 0.353 |

AUROC on test windows that don't straddle two states (pure arm): 0.688, against 0.688 on all test windows.

## Per patient (mean over seeds)

| Patient | frozen | train_pre10 | train_pre20 | train_pre45 | train_pre60 | pure | per_channel | blend_patient |
|---|---|---|---|---|---|---|---|---|
| chbmit:chb01 | 0.585 | 0.583 | 0.632 | 0.680 | 0.633 | 0.626 | 0.626 | 0.601 |
| chbmit:chb02 | 0.602 | 0.801 | 0.505 | 0.700 | 0.406 | 0.454 | 0.789 | 0.575 |
| chbmit:chb03 | 0.693 | 0.791 | 0.743 | 0.650 | 0.667 | 0.683 | 0.694 | 0.697 |
| chbmit:chb04 | 0.424 | 0.431 | 0.405 | 0.444 | 0.379 | 0.464 | 0.453 | 0.434 |
| chbmit:chb05 | 0.704 | 0.804 | 0.743 | 0.769 | 0.792 | 0.767 | 0.743 | 0.750 |
| chbmit:chb06 | 0.695 | 0.667 | 0.658 | 0.668 | 0.650 | 0.659 | 0.694 | 0.684 |
| chbmit:chb07 | 0.626 | 0.538 | 0.641 | 0.644 | 0.606 | 0.659 | 0.587 | 0.610 |
| chbmit:chb09 | 0.490 | 0.485 | 0.502 | 0.460 | 0.507 | 0.467 | 0.503 | 0.472 |
| chbmit:chb10 | 0.691 | 0.761 | 0.701 | 0.643 | 0.696 | 0.691 | 0.671 | 0.716 |
| chbmit:chb13 | 0.873 | 0.855 | 0.874 | 0.837 | 0.808 | 0.849 | 0.891 | 0.850 |
| chbmit:chb14 | 0.683 | 0.609 | 0.650 | 0.697 | 0.692 | 0.663 | 0.694 | 0.729 |
| chbmit:chb15 | 0.542 | 0.552 | 0.564 | 0.593 | 0.591 | 0.510 | 0.588 | 0.542 |
| chbmit:chb16 | 0.726 | 0.725 | 0.682 | 0.765 | 0.745 | 0.640 | 0.750 | 0.740 |
| chbmit:chb17 | 0.839 | 0.778 | 0.834 | 0.813 | 0.624 | 0.815 | 0.829 | 0.829 |
| chbmit:chb18 | 0.505 | 0.519 | 0.610 | 0.617 | 0.586 | 0.440 | 0.452 | 0.513 |
| chbmit:chb19 | 0.918 | 0.927 | 0.892 | 0.896 | nan | 0.903 | 0.820 | 0.945 |
| chbmit:chb20 | 0.754 | 0.608 | 0.629 | 0.690 | 0.699 | 0.774 | 0.717 | 0.789 |
| chbmit:chb22 | 0.479 | 0.575 | 0.597 | 0.375 | 0.479 | 0.378 | 0.458 | 0.479 |
| chbmit:chb23 | 0.913 | 0.841 | 0.886 | 0.922 | 0.888 | 0.899 | 0.922 | 0.921 |
| siena:PN01 | 0.973 | 0.988 | 0.998 | 0.950 | 0.875 | 0.997 | 0.999 | 0.977 |
| siena:PN03 | 0.855 | 0.547 | 0.618 | 0.789 | 0.673 | 0.851 | 0.887 | 0.854 |
| siena:PN14 | 0.945 | 0.943 | 0.941 | 0.938 | 0.922 | 0.942 | 0.951 | 0.924 |

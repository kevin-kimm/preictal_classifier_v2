# D2 improvement round: challengers to the frozen design (seizeit2)

Generated 2026-10-30T01:06:08 · docs/evaluation_methods.md v1.25, Section 14.2. Every arm is scored on the same test windows with the frozen labels. Adoption rule (Section 14.3): mean AUROC at least 0.01 above the frozen design on the pooled development patients, and higher in more than half of them.

| Arm | Patients | Seeds | Mean AUROC | 95% CI | Change vs frozen | Higher than frozen in | Wilcoxon p |
|---|---|---|---|---|---|---|---|
| Frozen design | 14 | 2 | 0.666 | 0.581–0.746 | – | – | – |
| Trained with a 10 min preictal period | 14 | 2 | 0.679 | 0.601–0.746 | +0.013 | 5 of 14 | 0.715 |
| Trained with a 20 min preictal period | 14 | 2 | 0.674 | 0.584–0.751 | +0.008 | 7 of 14 | 0.426 |
| Trained with a 45 min preictal period | 14 | 2 | 0.672 | 0.584–0.750 | +0.005 | 8 of 14 | 0.855 |
| Trained with a 60 min preictal period | 13 | 2 | 0.684 | 0.584–0.773 | +0.003 | 8 of 13 | 0.635 |
| Preictal length chosen per patient (nested) | 5 | 2 | 0.668 | 0.517–0.804 | +0.003 | 3 of 5 | – |
| Trained without windows that straddle two states | 14 | 2 | 0.655 | 0.553–0.745 | -0.011 | 6 of 14 | 0.502 |
| Plus infra-slow features | 14 | 2 | 0.679 | 0.602–0.751 | +0.012 | 8 of 14 | 0.0906 |
| Plus per-channel features | 14 | 2 | 0.711 | 0.659–0.764 | +0.045 | 11 of 14 | 0.0353 |
| Average of the frozen model and a patient-only model | 14 | 2 | 0.668 | 0.587–0.744 | +0.002 | 7 of 14 | 1 |
| Plus per-channel and infra-slow features (combination) | 14 | 2 | 0.721 | 0.669–0.774 | +0.055 | 12 of 14 | 0.00171 |

AUROC on test windows that don't straddle two states (pure arm): 0.655, against 0.655 on all test windows.

Training preictal lengths chosen per fold (pp_length): 10 min: 3, 20 min: 5, 30 min: 25, 45 min: 13, 60 min: 23.

## Per patient (mean over seeds)

| Patient | frozen | train_pre10 | train_pre20 | train_pre45 | train_pre60 | pp_length | pure | slow | per_channel | blend_patient | per_channel_slow |
|---|---|---|---|---|---|---|---|---|---|---|---|
| seizeit2:sub-001 | 0.657 | 0.535 | 0.672 | 0.693 | 0.723 | 0.634 | 0.658 | 0.642 | 0.674 | 0.659 | 0.689 |
| seizeit2:sub-002 | 0.810 | 0.795 | 0.805 | 0.841 | 0.829 | 0.818 | 0.822 | 0.827 | 0.822 | 0.819 | 0.834 |
| seizeit2:sub-005 | 0.378 | 0.539 | 0.443 | 0.306 | 0.275 | 0.378 | 0.405 | 0.396 | 0.527 | 0.377 | 0.486 |
| seizeit2:sub-029 | 0.618 | 0.605 | 0.612 | 0.644 | 0.594 | 0.642 | 0.615 | 0.604 | 0.650 | 0.610 | 0.666 |
| seizeit2:sub-034 | 0.863 | 0.862 | 0.880 | 0.895 | 0.878 | 0.870 | 0.879 | 0.868 | 0.872 | 0.865 | 0.869 |
| seizeit2:sub-053 | 0.362 | 0.323 | 0.285 | 0.535 | 0.374 | nan | 0.231 | 0.442 | 0.629 | 0.363 | 0.663 |
| seizeit2:sub-065 | 0.842 | 0.741 | 0.828 | 0.837 | 0.739 | nan | 0.810 | 0.839 | 0.867 | 0.826 | 0.865 |
| seizeit2:sub-073 | 0.833 | 0.828 | 0.827 | 0.849 | 0.858 | nan | 0.831 | 0.832 | 0.824 | 0.848 | 0.828 |
| seizeit2:sub-074 | 0.646 | 0.660 | 0.702 | 0.677 | 0.681 | nan | 0.669 | 0.664 | 0.684 | 0.673 | 0.670 |
| seizeit2:sub-086 | 0.468 | 0.779 | 0.527 | 0.425 | nan | nan | 0.410 | 0.489 | 0.581 | 0.524 | 0.614 |
| seizeit2:sub-100 | 0.693 | 0.746 | 0.677 | 0.631 | 0.783 | nan | 0.677 | 0.710 | 0.650 | 0.680 | 0.695 |
| seizeit2:sub-103 | 0.684 | 0.640 | 0.662 | 0.628 | 0.653 | nan | 0.679 | 0.676 | 0.659 | 0.655 | 0.672 |
| seizeit2:sub-112 | 0.746 | 0.710 | 0.764 | 0.691 | 0.782 | nan | 0.719 | 0.739 | 0.759 | 0.732 | 0.767 |
| seizeit2:sub-113 | 0.726 | 0.739 | 0.751 | 0.749 | 0.726 | nan | 0.761 | 0.771 | 0.755 | 0.720 | 0.782 |

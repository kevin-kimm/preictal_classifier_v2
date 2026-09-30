# Personalized models (characterization)

Generated 2026-09-30T09:12:13 · seeds [0] · 14 patients · docs/evaluation_methods.md v1.4, Section 11.1 (and v1.6, Section 11.3). Every variant is scored on the same test windows.

| Model | Mean AUROC | 95% CI | Beats the patient's clock-only model | p (vs clock only) |
|---|---|---|---|---|
| Other patients only, EEG (feature set v2, personal baseline, no time of day, 10 min context) | 0.516 | 0.409–0.602 | – | nan |
| Other patients + this patient, EEG (feature set v2, personal baseline, no time of day, 10 min context) | 0.669 | 0.585–0.743 | – | nan |

## Paired comparisons (per patient, mean over seeds)

| Comparison | Patients where the first is higher | Wilcoxon p |
|---|---|---|
| Other patients + this patient, EEG (feature set v2, personal baseline, no time of day, 10 min context) vs Other patients only, EEG (feature set v2, personal baseline, no time of day, 10 min context) | 13 of 14 | 0.00403 |

## Per patient (mean over seeds)

| Patient | Seizures | Other patients only, EEG (feature set v2, personal baseline, no time of day, 10 min context) | Other patients + this patient, EEG (feature set v2, personal baseline, no time of day, 10 min context) |
|---|---|---|---|
| seizeit2:sub-034 | 23 | 0.420 | 0.868 |
| seizeit2:sub-065 | 2 | 0.845 | 0.850 |
| seizeit2:sub-073 | 47 | 0.531 | 0.823 |
| seizeit2:sub-002 | 14 | 0.570 | 0.795 |
| seizeit2:sub-112 | 7 | 0.659 | 0.754 |
| seizeit2:sub-113 | 9 | 0.676 | 0.732 |
| seizeit2:sub-100 | 2 | 0.653 | 0.694 |
| seizeit2:sub-103 | 10 | 0.320 | 0.687 |
| seizeit2:sub-001 | 4 | 0.620 | 0.660 |
| seizeit2:sub-074 | 9 | 0.490 | 0.627 |
| seizeit2:sub-029 | 4 | 0.517 | 0.624 |
| seizeit2:sub-086 | 3 | 0.341 | 0.472 |
| seizeit2:sub-053 | 2 | 0.051 | 0.438 |
| seizeit2:sub-005 | 2 | 0.533 | 0.350 |

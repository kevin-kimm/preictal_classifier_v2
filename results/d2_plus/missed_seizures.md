# Seizure detection, seizure by seizure (D1 model)

Generated 2026-10-26T20:14:16 · seed 0 · D1 model and folds, unchanged · docs/evaluation_methods.md v1.25, Section 14.8.

151 annotated seizures in the test patients; 108 have at least one window entirely inside them; 43 are shorter than one window (about 30 s) and can't be scored this way. Seizures of the 25 test patients only.

| Group | Seizures | Median per-seizure AUROC | Detected well (AUROC ≥ 0.9) | Poorly (< 0.7) |
|---|---|---|---|---|
| All scored seizures | 108 | 0.965 | 57% | 32% |
| chbmit | 101 | 0.937 | 54% | 35% |
| siena | 7 | 0.995 | 100% | 0% |
| Shorter than 60 s | 36 | 0.981 | 56% | 31% |
| 60 s or longer | 72 | 0.941 | 58% | 33% |

## Worst and best detected

| Seizure | Patient | Onset (h into timeline) | Approx. duration (s) | Windows inside | AUROC | Median ictal probability |
|---|---|---|---|---|---|---|
| 107 | chbmit:chb13 | 76.58 | 64 | 7 | 0.021 | 0.004 |
| 109 | chbmit:chb13 | 77.09 | 56 | 6 | 0.059 | 0.009 |
| 136 | chbmit:chb15 | 72.62 | 32 | 1 | 0.060 | 0.002 |
| 2 | chbmit:chb01 | 26.23 | 38 | 2 | 0.125 | 0.002 |
| 135 | chbmit:chb15 | 72.27 | 71 | 9 | 0.128 | 0.003 |
| 105 | chbmit:chb13 | 74.27 | 61 | 7 | 0.216 | 0.034 |
| 3 | chbmit:chb01 | 27.03 | 50 | 5 | 0.260 | 0.008 |
| 39 | chbmit:chb08 | 13.22 | 170 | 29 | 0.261 | 0.003 |
| 40 | chbmit:chb08 | 16.28 | 189 | 32 | 0.269 | 0.003 |
| 4 | chbmit:chb01 | 29.23 | 90 | 13 | 0.271 | 0.004 |
| 37 | chbmit:chb07 | 60.69 | 95 | 14 | 1.000 | 0.992 |
| 46 | chbmit:chb09 | 46.93 | 69 | 8 | 1.000 | 0.992 |
| 47 | chbmit:chb09 | 86.05 | 61 | 7 | 1.000 | 0.995 |
| 56 | chbmit:chb11 | 80.56 | 30 | 1 | 1.000 | 0.974 |
| 157 | chbmit:chb19 | 97.24 | 76 | 10 | 1.000 | 0.960 |

Figure: `results/d2_plus/missed_seizures.png`

**Reading the figure.** Columns are seizures: the three the model detected worst (left) and best (right). Each shows 20 s before to 40 s after the annotated onset (dashed line), filtered 0.5–40 Hz, with the model's ictal probability below. Things to look for: whether the poorly detected seizures are visible on these scalp channels at all, whether they are short, and whether the rhythm looks like the seizures the model saw from other patients.

# Answers from existing results (D2 improvement round, part 1)

Generated 2026-10-26T20:11:48 · docs/evaluation_methods.md v1.25, Section 14.1. No model was trained; every number comes from result files already committed.

## 1. Alarm-level PPV and NPV

**PPV** answers: *when the alarm goes off, how often does a seizure follow within 30 min?* **NPV** answers: *when there is no warning, how often is the next 30 min seizure-free?* Both are pooled over patients for each seed, then averaged over seeds. Where true alarms weren't saved, PPV counts warned seizures as the true alarms (at most slightly low), and NPV is approximated from the counts (see the docstring).

| Result | Model | Target | Warned | False alarms / 24 h | Chance | p | PPV | NPV | Seizures / day in the data |
|---|---|---|---|---|---|---|---|---|---|
| D1, cross-patient (25 patients; D1 alarm rule, target ≤ 10) | D1 model | ≤ 10 | 0.21 | 10.61 | 0.198 | 0.43 | 0.062 | 0.9433 | 2.67 |
| Frozen design, CHB-MIT and Siena development (22 patients) | Frozen design (other patients + this patient) | ≤ 5 | 0.16 | 3.43 | 0.069 | 0.0028 | 0.176 | 0.9185 | 4.27 |
| Frozen design, CHB-MIT and Siena development (22 patients) | Frozen design (other patients + this patient) | ≤ 1 | 0.09 | 1.41 | 0.029 | 0.003 | 0.235 | 0.9162 | 4.27 |
| Frozen design, CHB-MIT and Siena development (22 patients) | Other patients only | ≤ 5 | 0.04 | 4.76 | 0.094 | 0.98 | 0.041 | 0.9060 | 4.27 |
| Frozen design, CHB-MIT and Siena development (22 patients) | Other patients only | ≤ 1 | 0.03 | 1.76 | 0.036 | 0.75 | 0.067 | 0.9102 | 4.27 |
| Frozen design, SeizeIT2 development dry run (14 patients) | Frozen design (other patients + this patient) | ≤ 5 | 0.46 | 4.58 | 0.091 | 2.5e-28 | 0.279 | 0.9536 | 3.59 |
| Frozen design, SeizeIT2 development dry run (14 patients) | Frozen design (other patients + this patient) | ≤ 1 | 0.20 | 1.71 | 0.035 | 1.7e-13 | 0.314 | 0.9372 | 3.59 |
| Frozen design, SeizeIT2 development dry run (14 patients) | Other patients only | ≤ 5 | 0.09 | 5.13 | 0.101 | 0.71 | 0.063 | 0.9238 | 3.59 |
| Frozen design, SeizeIT2 development dry run (14 patients) | Other patients only | ≤ 1 | 0.03 | 1.51 | 0.031 | 0.59 | 0.071 | 0.9251 | 3.59 |
| Frozen design, SeizeIT2 lockbox (20 patients, alarm part) | Frozen design (other patients + this patient) | ≤ 5 | 0.38 | 5.83 | 0.114 | 6.7e-10 | 0.098 | 0.9765 | 1.59 |
| Frozen design, SeizeIT2 lockbox (20 patients, alarm part) | Frozen design (other patients + this patient) | ≤ 1 | 0.18 | 1.69 | 0.035 | 4.3e-07 | 0.149 | 0.9716 | 1.59 |
| Frozen design, SeizeIT2 lockbox (20 patients, alarm part) | Other patients only | ≤ 5 | 0.12 | 4.88 | 0.096 | 0.34 | 0.037 | 0.9673 | 1.59 |
| Frozen design, SeizeIT2 lockbox (20 patients, alarm part) | Other patients only | ≤ 1 | 0.06 | 1.29 | 0.026 | 0.056 | 0.076 | 0.9680 | 1.59 |

### At home seizure rates

Hospital recordings have many more seizures per day than daily life (often after medication is reduced), which flatters PPV. If the same sensitivity and false-alarm rate held at home:

| Result | Model | Target | PPV, 1 a day | PPV, 1 a week | PPV, 1 a month | NPV, 1 a day | NPV, 1 a week | NPV, 1 a month |
|---|---|---|---|---|---|---|---|---|
| D1, cross-patient (25 patients; D1 alarm rule, target ≤ 10) | D1 model | ≤ 10 | 0.019 | 0.003 | 0.001 | 0.9787 | 0.9970 | 0.9993 |
| Frozen design, CHB-MIT and Siena development (22 patients) | Frozen design (other patients + this patient) | ≤ 5 | 0.044 | 0.006 | 0.002 | 0.9810 | 0.9973 | 0.9994 |
| Frozen design, SeizeIT2 development dry run (14 patients) | Frozen design (other patients + this patient) | ≤ 5 | 0.090 | 0.014 | 0.003 | 0.9873 | 0.9982 | 0.9996 |
| Frozen design, SeizeIT2 lockbox (20 patients, alarm part) | Frozen design (other patients + this patient) | ≤ 5 | 0.062 | 0.009 | 0.002 | 0.9853 | 0.9979 | 0.9995 |

**Reading these numbers.** NPV is close to 1 for any device, even one that never alarms, because almost every 30 min stretch is seizure-free. PPV is low whenever seizures are rare, even for a good device. That is why neither is a pass/fail criterion (evaluation methods, Section 8): they depend on how often the person has seizures as much as on the device. Sensitivity, false alarms per 24 h and the chance comparison don't.

## 2. D1 window-level confusion matrix

The D1 model's most likely class for every test window, against the true label, summed over the 25 test patients and averaged over seeds. Rows are the truth, columns the prediction.

| True \ predicted | preictal | ictal | interictal | Row total |
|---|---|---|---|---|
| preictal | 11,724 | 6,038 | 21,839 | 39,600 |
| ictal | 309 | 899 | 868 | 2,076 |
| interictal | 114,831 | 43,221 | 262,406 | 420,458 |

As shares of each row:

| True \ predicted | preictal | ictal | interictal |
|---|---|---|---|
| preictal | 29.6% | 15.2% | 55.1% |
| ictal | 14.9% | 43.3% | 41.8% |
| interictal | 27.3% | 10.3% | 62.4% |

Preictal vs interictal windows only ("positive" = predicted preictal):

* sensitivity 0.296, specificity 0.727;
* PPV 0.093 and NPV 0.916, with 8.6% of these windows preictal.

The most likely class isn't how alarms work (they use a threshold on the preictal probability), so this shows what the model leans towards rather than alarm performance. The new runs report the same table at each alarm threshold.

## 3. Seed variability

The instructor's question: why would the seed matter so much with a large dataset? The table separates two things. **Overall**: how much the mean over patients moves between seeds. **Per patient**: how much one patient's AUROC moves. A patient's score rests on a handful of seizures, and windows from the same seizure are strongly correlated, so the real sample size per patient is the number of seizures (about 2 to 10), not the number of windows (thousands). Averaging over many patients cancels most of that noise; picking each patient's best seed adds it all up in one direction.

| Result | Patients | Seeds | Mean AUROC | Overall: SD across seeds | Overall: range | Per patient: mean SD | Per patient: mean range | Per patient: largest range | Mean if each patient's best seed is kept |
|---|---|---|---|---|---|---|---|---|---|
| D1 cross-patient | 25 | 5 | 0.556 | 0.0079 | 0.019 | 0.047 | 0.116 | 0.265 | 0.614 |
| Other patients + this patient (`personalized.csv`) | 22 | 5 | 0.698 | 0.0043 | 0.011 | 0.013 | 0.032 | 0.093 | 0.714 |
| Other patients + this patient (`personalized_dev_cautious.csv`) | 22 | 5 | 0.677 | 0.0066 | 0.016 | 0.018 | 0.045 | 0.225 | 0.701 |
| Other patients + this patient (`personalized_dev_ctx10.csv`) | 22 | 5 | 0.700 | 0.0075 | 0.020 | 0.027 | 0.069 | 0.200 | 0.735 |
| Other patients + this patient (`personalized_dev_ctx30.csv`) | 22 | 5 | 0.654 | 0.0052 | 0.013 | 0.042 | 0.104 | 0.325 | 0.706 |
| Other patients + this patient (`personalized_dev_share75.csv`) | 22 | 5 | 0.688 | 0.0056 | 0.015 | 0.020 | 0.050 | 0.266 | 0.709 |
| Other patients + this patient (`personalized_dev_train1h.csv`) | 22 | 5 | 0.684 | 0.0067 | 0.018 | 0.021 | 0.052 | 0.236 | 0.708 |
| Other patients + this patient (`personalized_sens_gap1h.csv`) | 33 | 5 | 0.698 | 0.0040 | 0.009 | 0.023 | 0.057 | 0.199 | 0.725 |
| Other patients + this patient (`personalized_v2.csv`) | 22 | 5 | 0.696 | 0.0043 | 0.009 | 0.016 | 0.039 | 0.146 | 0.715 |
| Other patients + this patient (`personalized_v2_baseline.csv`) | 22 | 5 | 0.709 | 0.0060 | 0.014 | 0.017 | 0.041 | 0.116 | 0.729 |
| Other patients + this patient (`personalized_v2_baseline_noclock.csv`) | 22 | 5 | 0.681 | 0.0048 | 0.012 | 0.016 | 0.041 | 0.202 | 0.701 |

With only 5 seeds, keeping each patient's best already raises the mean; v1 kept the best of 297, which is why its 0.713 fell to 0.568 when run once (`scripts/demo_best_of_seeds.py`).

## 4. Channel subsets (VT-12)

| Channels | Seed 0 | Seed 1 | Seed 2 | Seed 3 | Seed 4 | Mean |
|---|---|---|---|---|---|---|
| all | 0.553 | 0.554 | 0.564 | 0.545 | 0.564 | 0.556 |
| random_half | 0.564 | 0.578 | 0.580 | 0.567 | 0.578 | 0.573 |
| cyton | 0.564 | 0.572 | 0.572 | 0.573 | 0.571 | 0.570 |

| Comparison | Patients where the subset is higher | Mean difference | Wilcoxon p |
|---|---|---|---|
| random_half vs all | 14 of 25 | +0.017 | 0.059 |
| cyton vs all | 16 of 25 | +0.014 | 0.200 |

A model at AUROC 0.556 has almost no signal, so which channels it sees barely matters, and a difference of about 0.015 is within patient-to-patient noise unless the p value says otherwise. Fewer channels can also make the pooled features (mean, SD, min and max across channels) less noisy, which can help a near-chance model slightly.


# Alarms, PPV and NPV: frozen (chbmit_siena)

Generated 2026-11-01T08:32:28 · docs/evaluation_methods.md v1.25, Sections 14.4–14.5. Thresholds from each fold's training data only; frozen alarm settings (risk averaged over 36 windows, above threshold for 6 in a row, 30 min refractory period) unless stated. Pooled over patients per seed, then averaged over seeds.

## Alarms and PPV/NPV (30 min warning window)

| Arm | Target | Seizures warned | False alarms / 24 h | Chance | p | Alarm PPV | Time PPV | Time NPV | Patients with a seizure warned |
|---|---|---|---|---|---|---|---|---|---|
| frozen | ≤ 5 | 0.15 (14/93) | 3.18 | 0.064 | 0.0023 | 0.182 | 0.188 | 0.9196 | 9.0 of 22 |
| frozen | ≤ 1 | 0.09 (8/93) | 1.21 | 0.025 | 0.0023 | 0.250 | 0.292 | 0.9182 | 5.0 of 22 |

**Alarm PPV**: true alarms ÷ all alarms. **Time PPV**: of the time a warning was on, the share followed by a seizure within 30 min. **Time NPV**: of the time without a warning, the share with no seizure in the next 30 min. Hospital recordings have far more seizures per day than daily life; at home rates:

| Target | PPV, 1 a day | PPV, 1 a week | PPV, 1 a month | NPV, 1 a day | NPV, 1 a week | NPV, 1 a month |
|---|---|---|---|---|---|---|
| ≤ 5 | 0.045 | 0.007 | 0.002 | 0.9810 | 0.9973 | 0.9994 |
| ≤ 1 | 0.066 | 0.010 | 0.002 | 0.9804 | 0.9972 | 0.9993 |

## Confusion matrices

Windows, at each fold's alarm threshold on the raw score (no smoothing), summed over patients and averaged over seeds. Positive = preictal.

| Target | True preictal, flagged | True preictal, missed | Interictal, flagged | Interictal, not flagged | Sensitivity | Specificity | PPV | NPV |
|---|---|---|---|---|---|---|---|---|
| ≤ 5 | 2,836 | 30,318 | 8,960 | 333,796 | 0.086 | 0.974 | 0.240 | 0.917 |
| ≤ 1 | 1,835 | 31,319 | 3,579 | 339,177 | 0.055 | 0.990 | 0.339 | 0.915 |

Time with and without a warning (alarm logic applied), as windows:

| Target | Warning on, seizure ahead | Warning on, none ahead | No warning, seizure ahead | No warning, none ahead |
|---|---|---|---|---|
| ≤ 5 | 5,113 | 22,016 | 28,041 | 320,740 |
| ≤ 1 | 3,329 | 8,091 | 29,825 | 334,665 |

## Warning window length (the instructor's comment on timing)

Same model and thresholds; only the warning window changes. Chance is recomputed for each window, so shorter windows are judged fairly. "Early alarms" are alarms in the hour before a seizure that come too early to count for that window length; they aren't in the false-alarm rate, so the PPV including them is the stricter one.

| Warning window | Target | Seizures warned | False alarms / 24 h | Chance | p | Times chance | Early alarms per seizure | Alarm PPV | PPV incl. early |
|---|---|---|---|---|---|---|---|---|---|
| 10 min | ≤ 5 | 0.02 | 3.18 | 0.022 | 0.6 | 1.0 | 0.27 | 0.031 | 0.022 |
| 10 min | ≤ 1 | 0.03 | 1.21 | 0.008 | 0.043 | 3.9 | 0.19 | 0.111 | 0.067 |
| 20 min | ≤ 5 | 0.05 | 3.18 | 0.043 | 0.37 | 1.3 | 0.24 | 0.074 | 0.056 |
| 20 min | ≤ 1 | 0.04 | 1.21 | 0.017 | 0.07 | 2.6 | 0.16 | 0.143 | 0.093 |
| 30 min | ≤ 5 | 0.15 | 3.18 | 0.064 | 0.0023 | 2.4 | 0.20 | 0.182 | 0.146 |
| 30 min | ≤ 1 | 0.09 | 1.21 | 0.025 | 0.0023 | 3.5 | 0.14 | 0.250 | 0.178 |
| 45 min | ≤ 5 | 0.18 | 3.18 | 0.094 | 0.0059 | 1.9 | 0.10 | 0.232 | 0.209 |
| 45 min | ≤ 1 | 0.10 | 1.21 | 0.037 | 0.0077 | 2.6 | 0.09 | 0.294 | 0.238 |
| 60 min | ≤ 5 | 0.20 | 3.18 | 0.124 | 0.019 | 1.7 | 0.08 | 0.284 | 0.263 |
| 60 min | ≤ 1 | 0.13 | 1.21 | 0.049 | 0.002 | 2.6 | 0.05 | 0.400 | 0.356 |

## Alarm settings (target ≤ 5)

| Smoothing (windows) | Persistence (windows) | Seizures warned | False alarms / 24 h | Chance | Warned minus chance | p |
|---|---|---|---|---|---|---|
| 1 | 1 | 0.151 | 3.18 | 0.064 | +0.087 | 0.0023 |
| 1 | 3 | 0.161 | 3.18 | 0.064 | +0.097 | 0.0008 |
| 1 | 6 | 0.140 | 3.33 | 0.067 | +0.073 | 0.0089 |
| 1 | 12 | 0.161 | 3.33 | 0.067 | +0.094 | 0.0013 |
| 12 | 1 | 0.151 | 3.02 | 0.061 | +0.090 | 0.0015 |
| 12 | 3 | 0.161 | 3.02 | 0.061 | +0.100 | 0.00049 |
| 12 | 6 | 0.140 | 2.92 | 0.059 | +0.081 | 0.0032 |
| 12 | 12 | 0.151 | 3.08 | 0.062 | +0.089 | 0.0017 |
| 36 | 1 | 0.140 | 3.28 | 0.066 | +0.074 | 0.0079 |
| 36 | 3 | 0.140 | 3.18 | 0.064 | +0.076 | 0.0062 |
| 36 (frozen) | 6 | 0.151 | 3.18 | 0.064 | +0.087 | 0.0023 |
| 36 | 12 | 0.172 | 3.18 | 0.064 | +0.108 | 0.00026 |
| 72 | 1 | 0.151 | 3.33 | 0.067 | +0.084 | 0.0035 |
| 72 | 3 | 0.151 | 3.33 | 0.067 | +0.084 | 0.0035 |
| 72 | 6 | 0.161 | 3.33 | 0.067 | +0.094 | 0.0013 |
| 72 | 12 | 0.183 | 3.13 | 0.063 | +0.120 | 6.4e-05 |

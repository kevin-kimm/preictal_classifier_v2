# Alarms, PPV and NPV: frozen (seizeit2)

Generated 2026-11-01T08:33:10 · docs/evaluation_methods.md v1.25, Sections 14.4–14.5. Thresholds from each fold's training data only; frozen alarm settings (risk averaged over 36 windows, above threshold for 6 in a row, 30 min refractory period) unless stated. Pooled over patients per seed, then averaged over seeds.

## Alarms and PPV/NPV (30 min warning window)

| Arm | Target | Seizures warned | False alarms / 24 h | Chance | p | Alarm PPV | Time PPV | Time NPV | Patients with a seizure warned |
|---|---|---|---|---|---|---|---|---|---|
| frozen | ≤ 5 | 0.46 (61/134) | 4.58 | 0.091 | 2.5e-28 | 0.279 | 0.273 | 0.9513 | 11.0 of 14 |
| frozen | ≤ 1 | 0.20 (27/134) | 1.71 | 0.035 | 1.7e-13 | 0.314 | 0.308 | 0.9364 | 6.0 of 14 |

**Alarm PPV**: true alarms ÷ all alarms. **Time PPV**: of the time a warning was on, the share followed by a seizure within 30 min. **Time NPV**: of the time without a warning, the share with no seizure in the next 30 min. Hospital recordings have far more seizures per day than daily life; at home rates:

| Target | PPV, 1 a day | PPV, 1 a week | PPV, 1 a month | NPV, 1 a day | NPV, 1 a week | NPV, 1 a month |
|---|---|---|---|---|---|---|
| ≤ 5 | 0.090 | 0.014 | 0.003 | 0.9873 | 0.9982 | 0.9996 |
| ≤ 1 | 0.105 | 0.017 | 0.004 | 0.9827 | 0.9975 | 0.9994 |

## Confusion matrices

Windows, at each fold's alarm threshold on the raw score (no smoothing), summed over patients and averaged over seeds. Positive = preictal.

| Target | True preictal, flagged | True preictal, missed | Interictal, flagged | Interictal, not flagged | Sensitivity | Specificity | PPV | NPV |
|---|---|---|---|---|---|---|---|---|
| ≤ 5 | 12,023 | 36,033 | 20,021 | 576,356 | 0.250 | 0.966 | 0.375 | 0.941 |
| ≤ 1 | 5,348 | 42,708 | 7,712 | 588,665 | 0.111 | 0.987 | 0.409 | 0.932 |

Time with and without a warning (alarm logic applied), as windows:

| Target | Warning on, seizure ahead | Warning on, none ahead | No warning, seizure ahead | No warning, none ahead |
|---|---|---|---|---|
| ≤ 5 | 20,351 | 54,242 | 27,759 | 542,135 |
| ≤ 1 | 9,005 | 20,258 | 39,105 | 576,119 |

## Warning window length (the instructor's comment on timing)

Same model and thresholds; only the warning window changes. Chance is recomputed for each window, so shorter windows are judged fairly. "Early alarms" are alarms in the hour before a seizure that come too early to count for that window length; they aren't in the false-alarm rate, so the PPV including them is the stricter one.

| Warning window | Target | Seizures warned | False alarms / 24 h | Chance | p | Times chance | Early alarms per seizure | Alarm PPV | PPV incl. early |
|---|---|---|---|---|---|---|---|---|---|
| 10 min | ≤ 5 | 0.15 | 4.58 | 0.031 | 7.3e-09 | 4.8 | 0.84 | 0.112 | 0.069 |
| 10 min | ≤ 1 | 0.10 | 1.71 | 0.012 | 8.2e-09 | 8.3 | 0.43 | 0.181 | 0.100 |
| 20 min | ≤ 5 | 0.20 | 4.58 | 0.061 | 4.2e-08 | 3.3 | 0.78 | 0.146 | 0.093 |
| 20 min | ≤ 1 | 0.11 | 1.71 | 0.023 | 6.7e-07 | 4.8 | 0.40 | 0.203 | 0.117 |
| 30 min | ≤ 5 | 0.46 | 4.58 | 0.091 | 2.5e-28 | 5.0 | 0.62 | 0.279 | 0.202 |
| 30 min | ≤ 1 | 0.20 | 1.71 | 0.035 | 1.7e-13 | 5.8 | 0.34 | 0.314 | 0.205 |
| 45 min | ≤ 5 | 0.51 | 4.58 | 0.133 | 5.6e-26 | 3.9 | 0.41 | 0.333 | 0.271 |
| 45 min | ≤ 1 | 0.25 | 1.71 | 0.052 | 8.7e-15 | 4.9 | 0.23 | 0.410 | 0.313 |
| 60 min | ≤ 5 | 0.60 | 4.58 | 0.173 | 9e-29 | 3.5 | 0.25 | 0.413 | 0.366 |
| 60 min | ≤ 1 | 0.30 | 1.71 | 0.069 | 9.9e-16 | 4.3 | 0.16 | 0.473 | 0.398 |

## Alarm settings (target ≤ 5)

| Smoothing (windows) | Persistence (windows) | Seizures warned | False alarms / 24 h | Chance | Warned minus chance | p |
|---|---|---|---|---|---|---|
| 1 | 1 | 0.448 | 4.52 | 0.090 | +0.358 | 1.1e-27 |
| 1 | 3 | 0.440 | 4.43 | 0.088 | +0.352 | 3.5e-27 |
| 1 | 6 | 0.470 | 4.61 | 0.091 | +0.379 | 4.7e-30 |
| 1 | 12 | 0.463 | 4.46 | 0.089 | +0.374 | 7.7e-30 |
| 12 | 1 | 0.455 | 4.52 | 0.090 | +0.366 | 1.3e-28 |
| 12 | 3 | 0.463 | 4.46 | 0.089 | +0.374 | 7.7e-30 |
| 12 | 6 | 0.448 | 4.55 | 0.090 | +0.358 | 1.5e-27 |
| 12 | 12 | 0.440 | 4.58 | 0.091 | +0.350 | 1.7e-26 |
| 36 | 1 | 0.448 | 4.64 | 0.092 | +0.356 | 4e-27 |
| 36 | 3 | 0.440 | 4.64 | 0.092 | +0.348 | 3.1e-26 |
| 36 (frozen) | 6 | 0.455 | 4.58 | 0.091 | +0.364 | 2.5e-28 |
| 36 | 12 | 0.463 | 4.58 | 0.091 | +0.372 | 3e-29 |
| 72 | 1 | 0.448 | 4.75 | 0.094 | +0.354 | 1.4e-26 |
| 72 | 3 | 0.440 | 4.72 | 0.093 | +0.347 | 7.8e-26 |
| 72 | 6 | 0.440 | 4.72 | 0.093 | +0.347 | 7.8e-26 |
| 72 | 12 | 0.448 | 4.69 | 0.093 | +0.355 | 7.4e-27 |

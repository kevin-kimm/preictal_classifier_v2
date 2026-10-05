# Continuous personalization, simulated forward in time (SeizeIT2 development patients)

Generated 2026-10-05T08:56:05 · seed 0 · 25 patients, 126 steps · docs/evaluation_methods.md v1.19. Each step is scored only on the time after it was trained.

| Seizures learned | Steps | AUROC, learning device | AUROC, general + baseline only | Warned (≤ 5 / 24 h), learning device | False alarms / 24 h | Warned, general only | False alarms / 24 h |
|---|---|---|---|---|---|---|---|
| 0 | 23 | 0.530 (0.44–0.61, n=19) | 0.530 (0.44–0.61, n=19) | 0.26 (n=23) | 6.22 | 0.26 (n=23) | 6.22 |
| 1 | 16 | 0.606 (0.44–0.79, n=9) | 0.497 (0.31–0.68, n=9) | 0.54 (n=13) | 12.95 | 0.31 (n=13) | 11.16 |
| 2 | 11 | 0.512 (0.28–0.74, n=5) | 0.289 (0.18–0.38, n=5) | 0.25 (n=8) | 4.75 | 0.00 (n=8) | 6.65 |
| 3 | 8 | 0.834 (0.69–0.93, n=3) | 0.573 (0.40–0.84, n=3) | 0.43 (n=7) | 3.80 | 0.29 (n=7) | 3.80 |
| 4 | 6 | 0.719 (0.72–0.72, n=1) | 0.245 (0.25–0.25, n=1) | 0.40 (n=5) | – | 0.00 (n=5) | – |
| 5+ | 62 | 0.580 (0.44–0.70, n=13) | 0.476 (0.35–0.60, n=13) | 0.35 (n=62) | 17.27 | 0.15 (n=62) | 3.80 |

## Fixed and adaptive thresholds, over all steps after at least one learned seizure

| Model | Threshold | Target | Seizures warned | False alarms / 24 h | Chance | p |
|---|---|---|---|---|---|---|
| learning device | fixed | ≤ 5 | 36/95 (0.38) | 13.77 | 0.249 | 0.00339 |
| learning device | fixed | ≤ 1 | 22/95 (0.23) | 9.18 | 0.174 | 0.091 |
| learning device | adaptive | ≤ 5 | 33/95 (0.35) | 10.24 | 0.192 | 0.000256 |
| learning device | adaptive | ≤ 1 | 23/95 (0.24) | 6.00 | 0.117 | 0.000522 |
| learning device, 75% personal | fixed | ≤ 5 | 32/95 (0.34) | 15.10 | 0.269 | 0.0874 |
| learning device, 75% personal | fixed | ≤ 1 | 12/95 (0.13) | 8.21 | 0.157 | 0.831 |
| learning device, 75% personal | adaptive | ≤ 5 | 33/95 (0.35) | 10.07 | 0.189 | 0.000189 |
| learning device, 75% personal | adaptive | ≤ 1 | 14/95 (0.15) | 4.33 | 0.086 | 0.0325 |
| learning device, patient only | fixed | ≤ 5 | 20/95 (0.21) | 9.45 | 0.178 | 0.241 |
| learning device, patient only | fixed | ≤ 1 | 8/95 (0.08) | 5.56 | 0.109 | 0.827 |
| learning device, patient only | adaptive | ≤ 5 | 19/95 (0.20) | 8.03 | 0.154 | 0.135 |
| learning device, patient only | adaptive | ≤ 1 | 8/95 (0.08) | 4.15 | 0.083 | 0.531 |
| never learns | fixed | ≤ 5 | 15/95 (0.16) | 6.97 | 0.135 | 0.297 |
| never learns | fixed | ≤ 1 | 7/95 (0.07) | 3.97 | 0.079 | 0.634 |
| never learns | adaptive | ≤ 5 | 13/95 (0.14) | 6.89 | 0.133 | 0.505 |
| never learns | adaptive | ≤ 1 | 6/95 (0.06) | 3.80 | 0.076 | 0.735 |

## v1.22 arms, over all steps after at least one learned seizure

Same models; only the threshold schedule differs. `strict24` and `fast_strict24` exist for the ≤ 5 setting only (they use the stricter of the ≤ 5 and ≤ 1 thresholds in the first 24 h after each retraining).

| Model | Arm | Target | Seizures warned | False alarms / 24 h | Chance | p |
|---|---|---|---|---|---|---|
| learning device | adaptive | ≤ 5 | 33/95 (0.35) | 10.24 | 0.192 | 0.000256 |
| learning device | fast | ≤ 5 | 27/95 (0.28) | 4.77 | 0.094 | 1.24e-07 |
| learning device | strict24 | ≤ 5 | 23/95 (0.24) | 6.62 | 0.129 | 0.00183 |
| learning device | fast_strict24 | ≤ 5 | 18/95 (0.19) | 2.91 | 0.059 | 9.67e-06 |
| learning device | adaptive | ≤ 1 | 23/95 (0.24) | 6.00 | 0.117 | 0.000522 |
| learning device | fast | ≤ 1 | 17/95 (0.18) | 2.47 | 0.050 | 4.69e-06 |
| learning device, 75% personal | adaptive | ≤ 5 | 33/95 (0.35) | 10.07 | 0.189 | 0.000189 |
| learning device, 75% personal | fast | ≤ 5 | 26/95 (0.27) | 4.50 | 0.089 | 1.65e-07 |
| learning device, 75% personal | strict24 | ≤ 5 | 14/95 (0.15) | 4.94 | 0.098 | 0.0777 |
| learning device, 75% personal | fast_strict24 | ≤ 5 | 14/95 (0.15) | 2.56 | 0.052 | 0.000386 |
| learning device, 75% personal | adaptive | ≤ 1 | 14/95 (0.15) | 4.33 | 0.086 | 0.0325 |
| learning device, 75% personal | fast | ≤ 1 | 13/95 (0.14) | 2.21 | 0.045 | 0.000327 |
| learning device, patient only | adaptive | ≤ 5 | 19/95 (0.20) | 8.03 | 0.154 | 0.135 |
| learning device, patient only | fast | ≤ 5 | 15/95 (0.16) | 3.36 | 0.067 | 0.0017 |
| learning device, patient only | strict24 | ≤ 5 | 8/95 (0.08) | 4.33 | 0.086 | 0.577 |
| learning device, patient only | fast_strict24 | ≤ 5 | 7/95 (0.07) | 2.03 | 0.041 | 0.0985 |
| learning device, patient only | adaptive | ≤ 1 | 8/95 (0.08) | 4.15 | 0.083 | 0.531 |
| learning device, patient only | fast | ≤ 1 | 7/95 (0.07) | 1.85 | 0.038 | 0.0686 |
| never learns | adaptive | ≤ 5 | 13/95 (0.14) | 6.89 | 0.133 | 0.505 |
| never learns | fast | ≤ 5 | 11/95 (0.12) | 5.56 | 0.109 | 0.465 |
| never learns | strict24 | ≤ 5 | 6/95 (0.06) | 4.50 | 0.089 | 0.861 |
| never learns | fast_strict24 | ≤ 5 | 7/95 (0.07) | 3.62 | 0.072 | 0.538 |
| never learns | adaptive | ≤ 1 | 6/95 (0.06) | 3.80 | 0.076 | 0.735 |
| never learns | fast | ≤ 1 | 7/95 (0.07) | 3.00 | 0.060 | 0.351 |

## v1.23 recipes: paired AUROC against the current blend, by learning stage

Steps where both models were scored. Positive differences favor the recipe.

| Recipe | Seizures learned | Steps | Recipe AUROC | Blend AUROC | Recipe higher | Wilcoxon p |
|---|---|---|---|---|---|---|
| personal75 | 1 or more | 31 | 0.631 | 0.606 | 18 of 31 | 0.272 |
| personal75 | 1–2 | 14 | 0.599 | 0.573 | 8 of 14 | 0.761 |
| personal75 | 3–4 | 4 | 0.785 | 0.805 | 1 of 4 | 0.25 |
| personal75 | 5 or more | 13 | 0.618 | 0.580 | 9 of 13 | 0.127 |
| patient_only | 1 or more | 28 | 0.676 | 0.624 | 18 of 28 | 0.131 |
| patient_only | 1–2 | 12 | 0.683 | 0.618 | 8 of 12 | 0.266 |
| patient_only | 3–4 | 3 | 0.700 | 0.834 | 1 of 3 | 0.75 |
| patient_only | 5 or more | 13 | 0.664 | 0.580 | 9 of 13 | 0.191 |

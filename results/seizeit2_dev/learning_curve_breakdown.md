# Continuous personalization, simulated forward in time (SeizeIT2 development patients)

Generated 2026-10-03T20:25:26 · seed 0 · 25 patients, 126 steps · docs/evaluation_methods.md v1.19. Each step is scored only on the time after it was trained.

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
| never learns | fixed | ≤ 5 | 15/95 (0.16) | 6.97 | 0.135 | 0.297 |
| never learns | fixed | ≤ 1 | 7/95 (0.07) | 3.97 | 0.079 | 0.634 |
| never learns | adaptive | ≤ 5 | 13/95 (0.14) | 6.89 | 0.133 | 0.505 |
| never learns | adaptive | ≤ 1 | 6/95 (0.06) | 3.80 | 0.076 | 0.735 |

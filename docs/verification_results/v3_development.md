# v3 development results

v3 is a personalized, adaptive algorithm (`docs/v3_scope.md`). It was developed after v2's final test. The SeizeIT2 lockbox has been used, so every result here is a **development result**, on CHB-MIT, Siena or the 25 SeizeIT2 development patients. None of them changes v2's reported results (`D2.md`). Each experiment was written into `docs/evaluation_methods.md`, with a decision rule, before it was run.

| Experiment | Evaluation methods | Status | Evidence |
|---|---|---|---|
| Adaptive alarm thresholds | v1.20, Section 11.10 | Improvement by the pre-set rule | `results/seizeit2_dev/learning_curve_adaptive.md` |
| Threshold schedules (Phase A, experiment 1) | v1.22 and v1.23, Section 11.12 | By the rule: `adaptive` kept; recorded deviation: `fast` to Phase B | `results/seizeit2_dev/learning_curve_arms.md` |
| Learning recipes (Phase A, experiment 2) | v1.23 and v1.24, Section 11.13 | 50% blend kept; patient-only becomes a Phase B secondary question | `results/seizeit2_dev/learning_curve_recipes.md` |
| False-alarm breakdown | v1.21, Section 11.11 | Reported | `results/seizeit2_dev/false_alarm_breakdown.md`, `alarm_log_breakdown.csv` |

## Findings

**F3-01. Adaptive thresholds cut false alarms by a quarter to a third, but not to target.** In the forward-in-time simulation, recalibrating the learning device's threshold every 6 h on recent confirmed-normal EEG lowered its false alarms from 13.8 to 10.2 per 24 h at the ≤ 5 target, while warning 35% of seizures instead of 38% (chance 19%, p = 0.0003). At the ≤ 1 target, false alarms fell from 9.2 to 6.0 per 24 h, and warnings went from no better than chance (23%, p = 0.09) to clearly better (24%, p = 0.0005). The never-learning model gained nothing. Both targets are still exceeded, so the breakdown (v1.21) looks for where the remaining false alarms come from.

**F3-02. Most remaining false alarms come in the first day after each retraining. Movement contributes, but less.** The simulation was rerun with alarm logging. It reproduced every earlier number exactly, and the 2,018 logged alarms matched its own counts in every configuration. Looking at the learning device's false alarms:

* **Time since retraining.** With adaptive thresholds at ≤ 5, the rates were 9.6 per 24 h in the 0–6 h after retraining, 12.3 at 6–24 h and 3.4 after 24 h. With fixed thresholds they were 9.6, 13.6 and 18.9. So recalibration fixed the long-term drift, but not the first day after each seizure, when the newly set threshold doesn't yet fit and recalibration must wait for 4 h of confirmed normal EEG. The higher rate at 5 or more learned seizures (12.1 per 24 h) is consistent with this, since frequent-seizure patients spend most of their time within a day of a seizure.
* **Patients.** Three patients produced 48% of the false alarms (adaptive, ≤ 5), but 13 patients had some, so they aren't confined to a few patients.
* **Movement.** 15–25% of the learning device's false alarms fell in the patient's most active 10% of time, judged by the wearable's accelerometer (fixed ≤ 5: 20%, p = 0.0001; adaptive ≤ 1: 21%, p = 0.007). EMG was slightly raised (14–18%), and the EEG-based muscle index was not (11–15%). The never-learning model's false alarms showed no such link.

The personal model seems to have partly learned movement-related patterns. Gating movement could therefore also cost true warnings. Removing every high-movement false alarm would cut them by only about a fifth, so the first-day problem comes first.

**F3-03. Hourly threshold recalibration halves false alarms and brings them under target, at a cost in warnings.** Recalibrating every hour on EEG at least 1 h old (`fast`), instead of every 6 h on EEG at least 4 h old, lowered the learning device's false alarms from 10.24 to 4.77 per 24 h at the ≤ 5 setting. That is the first schedule to meet the target in the forward-in-time simulation. It warned 28% of seizures instead of 35%, about 3 times chance against 1.8 times (p = 1.2×10⁻⁷). At the ≤ 1 setting it warned 18% at 2.47 per 24 h, 3.6 times chance. Adding a stricter first day after each seizure lowered false alarms further (2.91 per 24 h) but cost more warnings (19%).

By the pre-set rule (at most 5 percentage points fewer warnings), no arm qualified, so `adaptive` was retained. As a recorded deviation, `fast` was chosen for Phase B because it alone met the scope's false-alarm criterion (S2); see evaluation methods v1.23.

**F3-04. Per-patient models rank risk best but produce weaker alarms; the 50% blend stays.** At every step of the forward-in-time simulation, three recipes were trained on the same data.

* **AUROC.** Patient-only models had the highest AUROC: 0.676 against the blend's 0.624 on the same 28 steps, and 0.664 against 0.580 after 5 or more learned seizures. Neither difference was significant (p = 0.13 and 0.19). 75% personal weight scored about the same as 50% (0.631 against 0.606, p = 0.27).
* **Alarms** (`fast` schedule, ≤ 5). Patient-only models warned fewer seizures (16% against 28%) at fewer false alarms (3.4 against 4.8 per 24 h), and were less clearly better than chance (2.4 times against 3.0, p = 0.002 against 10⁻⁷).

A plausible reading: a model trained on one person's few hours ranks windows within a period well, but its scores are less stable from one period to the next, so thresholds carry over less well. The base data steadies them.

By the pre-set rule the 50% blend is kept. Because the AUROC trend favors per-patient models with more seizures, but 28 steps can't settle it, the comparison is pre-registered as a Phase B secondary question, where 100 patients give about four times the data.


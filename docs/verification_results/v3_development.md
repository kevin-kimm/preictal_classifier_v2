# v3 development results

v3 explores improvements after v2's final test. The SeizeIT2 lockbox has been used, so every result here is a **development result**, on CHB-MIT, Siena or the 25 SeizeIT2 development patients. None of them changes v2's reported results (`D2.md`). Each experiment was written into `docs/evaluation_methods.md`, with a decision rule, before it was run.

| Experiment | Evaluation methods | Status | Evidence |
|---|---|---|---|
| Adaptive alarm thresholds | v1.20, Section 11.10 | Improvement by the pre-set rule | `results/seizeit2_dev/learning_curve_adaptive.md` |
| False-alarm breakdown | v1.21, Section 11.11 | Planned | `results/seizeit2_dev/false_alarm_breakdown.md` |

## Findings

**F3-01. Adaptive thresholds cut false alarms by a quarter to a third, but not to target.** In the forward-in-time simulation, recalibrating the learning device's threshold every 6 h on recent confirmed-normal EEG lowered its false alarms from 13.8 to 10.2 per 24 h at the ≤ 5 target, while warning 35% of seizures instead of 38% (chance 19%, p = 0.0003). At the ≤ 1 target, false alarms fell from 9.2 to 6.0 per 24 h, and warnings went from no better than chance (23%, p = 0.09) to clearly better (24%, p = 0.0005). The never-learning model gained nothing. Both targets are still exceeded, so the breakdown (v1.21) looks for where the remaining false alarms come from.

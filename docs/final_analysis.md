# Final Analysis (Deliverable 2)

Kevin Kim · 2026-10-03 · preictal_classifier_v2

## 1. The question and the short answer

**Can scalp or wearable EEG warn a person with epilepsy that a seizure is likely within the next 30 minutes, reliably enough to be useful?**

Not yet. Every test points the same way:

* **Across people,** a model trained on other people barely beats guessing.
* **Personalized,** a model that also learns the wearer's own seizures finds a real, statistically solid signal. On 62 new patients with behind-the-ear EEG it reached AUROC 0.621 and warned 38% of seizures at 5.8 false alarms per 24 h, more than 3 times chance.
* **Compared with the course target** of 80% of seizures warned at no more than 5 false alarms per 24 h, that is well short of a device someone could rely on.

The results support one direction clearly: a device that keeps learning its wearer, with alarm thresholds that adapt over time.

## 2. How the results were obtained

The project was run as a design-controlled software-as-a-medical-device prototype:

* **Rules fixed before testing.** A verification plan with pass/fail criteria was frozen before any test (tag `vtp-1.0`). Every later choice was written into the evaluation methods before it was run (versions 1.0 to 1.19), including the corrections and deviations.
* **No test patient ever influenced a choice.** Cross-patient models were tested leaving one patient out, with thresholds set on separate inner patients. Personalized designs were tested leaving one seizure out, with buffers, and with every design choice made per fold or by a pre-set rule.
* **One final test on sealed data.** The design was frozen (tag `freeze-v1.13`) and tested once on 100 SeizeIT2 patients that nobody had looked at, under a protocol fixed beforehand (tags `lockbox-protocol-v1.17` and `lockbox-alarm-plan-v1.18`).
* **Honest baselines.** Results were compared with random alarms at the same false-alarm rate, and with a clock-only model, because the time of day alone predicts seizures in the hospital data.

Data: CHB-MIT and Siena (development, 37 patients), TUSZ and a mental-arithmetic set (false alarms), SeizeIT2 (25 development and 100 sealed patients, behind-the-ear wearable EEG).

## 3. Results, step by step

| Stage | Setting | Main result | Finding |
|---|---|---|---|
| D1 baseline | Cross-patient, 25 patients | AUROC 0.556; alarms at chance; a clock-only model scores 0.697 | F-18 to F-23 |
| D2 improvements | Cross-patient, nested selection | AUROC 0.614, but 0.528 without the time of day; alarms near chance | F2-01 to F2-06 |
| v1 (v6) comparison | Siena, as reported | Single run 0.568, matching v2; the reported 0.713 is explained by keeping the best of 297 seeds per test patient | F-25 to F-27 |
| Personalized, development | 22 CHB-MIT and Siena patients | Frozen design 0.700 (optimistic: chosen on these patients); other patients only 0.529 without the clock; own data helped 19 of 22 | F2-07 to F2-11 |
| Sensitivity: 1 h gap | 33 patients | Same patients 0.700 → 0.649; the definition of normal EEG matters by about 0.05 | F2-15 |
| SeizeIT2 dry run | 14 development patients | 0.669; alarms 46% at 4.6 per 24 h | F2-16 |
| **Final test: SeizeIT2 lockbox** | **62 new patients (alarms: 20)** | **AUROC 0.621 (0.564–0.671); other patients only 0.547; alarms 38% at 5.83 per 24 h (chance 11%)** | **F2-17** |
| Continuous learning, simulated | 25 SeizeIT2 development patients, forward in time | Learning beats not learning (0.606 against 0.454, p = 0.0015), but false alarms reach 13.8 per 24 h | F2-18 |

Details and evidence are in `docs/verification_results/D1.md` and `D2.md`.

## 4. What worked and what didn't

**Worked:**

1. **Personalization.** It was the one change that helped everywhere: CHB-MIT, Siena, SeizeIT2 development and the lockbox. The warning signs in EEG exist, but they differ from person to person.
2. **The engineering.** The pipeline harmonizes three hospitals' formats and a wearable's, runs on a laptop, and is covered by 187 automated tests. It reproduced the dry run exactly on the final data.
3. **The rigor.** The pre-registered testing and the sealed final test gave a number that can be trusted, and showed how optimistic the development numbers were (0.700 → 0.621).

**Didn't work:**

1. **Cross-patient prediction,** however it was improved: normalization, context, TUSZ data, a neural network, richer features.
2. **More data of the wrong kind.** Extra normal EEG, a looser normal-EEG definition for training, and a larger pool of other patients barely helped. The limit is seizures per person.
3. **Alarm calibration.** Thresholds learned from earlier EEG drift. False alarms came out above target in almost every test, and badly so in the forward-in-time simulation.

## 5. Are the results acceptable?

* **As a course deliverable:** VT-15 (+15% over D1) failed at +10.5%, and that gain came from the time of day. VT-17 (80% of seizures at ≤ 5 false alarms per 24 h) failed. VT-16 (alarm logic) passed. Both failures are explained by evidence rather than left open.
* **As a medical device:** no. Warning about a third of seizures, with around six false alarms a day, would neither protect a user nor keep their trust.
* **As evidence for what to build next:** yes. The results are consistent across four datasets and hold on sealed data. They identify where the real problem lies: personal data and adaptive calibration, not model complexity.

## 6. Threats to validity

* **Sample size.** The lockbox alarms rest on 20 patients and one seed; the AUROC on 62 patients and one seed. Seeds varied results by about ±0.007 throughout.
* **Protocol deviations, all recorded in the evaluation methods:**
  * the equivalence check ran after the lockbox AUROC part, and its first attempt compared nothing because of a shell quirk;
  * the alarm part was reduced to 20 patients because of a pessimistic run-time estimate;
  * in the frozen v2 features, two of eight left-right channel pairs never matched (a spelling erratum, kept so the frozen code stayed identical).
* **Labels.** Seizure onsets come from expert annotations. The 4 h definition of normal EEG affects results by about 0.05. SeizeIT2's anonymized clock times mean its files had to be placed in run order, with conservative rules.
* **Setting.** All recordings come from hospital monitoring, where people are often sleep-deprived or have reduced medication, which is unlike daily life with a consumer device.
* **Time of day.** It predicts seizures in hospital data partly because of how recordings are scheduled, so it was excluded from the final design. A real device knows the time, and a person's own daily seizure rhythm may be a genuine signal worth testing separately.

## 7. Recommendations

1. **Build AuraSense as a device that keeps learning its wearer.** Start from a general model and a calibration period, then retrain after each seizure (F2-18). Be honest with users that day-one prediction is near chance.
2. **Make alarm thresholds adaptive.** Recalibrate them continuously on recent normal EEG, and test that adaptation forward in time, since this is the main obstacle the simulation found.
3. **Collect seizure labels automatically.** Seizure detection is far easier than prediction (0.87 in D1), so the device could label its own seizures, with user confirmation, to keep learning.
4. **Target people with frequent seizures first,** where a personal model can learn quickly.
5. **Test personal daily and multi-day seizure rhythms,** using the device's real clock, as a separate, pre-planned experiment.
6. **Use the wearable's other sensors.** SeizeIT2 includes ECG, EMG and movement data, which could add heart-rate features and reject movement artifacts.
7. **Regulatory path.** A device that changes after release needs its updates specified and verified in advance. The FDA's approach to predetermined change control plans for AI-enabled devices fits this design.

## 8. Next

Deliverable 3 builds the local replay interface and the live OpenBCI Cyton test (VT-21 to VT-26). Its live sessions measure false alarms and system behavior on seizure-free EEG, using the general model and a 10-minute personal baseline.

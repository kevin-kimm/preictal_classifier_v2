# Evaluation Methods

| Doc | Version | Author | Written |
|---|---|---|---|
| EVM-001 | 1.2 | Kevin Kim | v1.0 on 2026-09-26, before any model was trained; v1.1 and v1.2 after D1, before any D2 result |

This document fixes how models are trained, tuned and scored for Deliverables 1 and 2. It adds detail to the verification plan (tag `vtp-1.0`) and doesn't change any of its pass/fail criteria. It is committed before any model is trained so the Git history shows these choices came first. Anything changed after results are seen goes in the version history (Section 11) with a reason.

## 1. What each dataset is used for

| Dataset | D1 training | D1 test patients | False-alarm testing |
|---|---|---|---|
| CHB-MIT | All 23 subjects | 21 eligible | Yes, through the cross-patient folds |
| Siena | All 14 subjects | 4 eligible | Yes, through the cross-patient folds |
| TUSZ | No (Section 6) | None: no eligible seizures (D1 finding F-13) | Yes: all interictal time, 1,052.8 h from 675 patients |
| Mental arithmetic | No | None | Yes: 2.4 h, a task-state check only (finding F-03) |
| TUAR | No | None | Artifact tests in D3 (VT-26) |

Eligible test patients are defined in the verification plan: at least one eligible seizure and at least 1 h of interictal data. Subjects who aren't eligible test patients are still used for training.

## 2. Windows and labels

30 s windows every 5 s, each labeled by its end time (`configs/default.yaml`, label report VT-07). Training uses preictal, ictal and interictal windows. Excluded windows are never used for training, but they are scored when evaluating alarms, because false alarms during excluded time still count (plan, Section 3).

## 3. Cross-validation

Leave-one-patient-out over the 25 eligible test patients (decision D-6: 25 is under the threshold of 40). Patients are grouped by subject, so chb01 and chb21 are always on the same side of a split.

In each fold:

1. The test patient is held out completely.
2. From the remaining subjects, 20% of those who are themselves eligible test patients (rounded to the nearest whole number, at least 2) form the inner validation set, drawn with the fold's seed. They need both preictal and interictal data for thresholds to be meaningful.
3. The model is trained on all other remaining CHB-MIT and Siena subjects.
4. The threshold is chosen on the inner validation set (Section 7).
5. Only then is the test patient scored.

## 4. Seeds

Seeds 0, 1, 2, 3 and 4 (plan, Section 4). The seed sets the inner validation draw and the model's random state. Every result is reported for all five seeds as mean ± SD, and no seed is dropped or replaced.

## 5. The D1 baseline model

The D1 model is fully specified here and is not tuned, so no choice can be influenced by test results. Richer options are D2 experiments (Section 10).

**Features, per derivation, per window.** Power spectrum by Welch's method (2 s Hann segments, 50% overlap), then:

| Feature | Count |
|---|---|
| Log absolute band power: delta 0.5–4, theta 4–8, alpha 8–13, beta 13–30, gamma 30–45 Hz | 5 |
| Relative band power (each band over 0.5–45 Hz) | 5 |
| Log line length, log variance | 2 |
| Hjorth mobility and complexity | 2 |
| Spectral edge frequency (90% of 0.5–45 Hz power) | 1 |

**Montage-agnostic pooling.** Each of the 15 features is summarized across the derivations present in that window by its mean, standard deviation, minimum and maximum, which gives 60 numbers whatever the number of channels. Absent derivations are ignored. The number of present derivations is deliberately not a feature, because it would reveal which dataset a window came from.

**Normalization.** None per patient in D1. Per-patient normalization is a D2 experiment.

**Classifier.** scikit-learn `HistGradientBoostingClassifier` with default settings and `random_state` set to the seed. It has three classes: preictal, ictal and interictal. The risk score is the predicted probability of preictal.

**Sample weights.** Each class gets the same total weight, and within a class, each subject counts equally. So a patient with many hours of EEG doesn't outweigh a patient with few.

## 6. Why TUSZ is not in D1 training

TUSZ has no usable preictal data (finding F-13), so in training it would add only interictal examples, about 64% of all interictal time. TUSZ recordings also differ systematically from CHB-MIT and Siena: a different hospital and different equipment, more routine daytime clinic EEG, and missing channels in 625 recordings. A model could then learn "looks like a TUSZ recording, so no seizure coming", which is a fingerprint of the dataset rather than a sign of an approaching seizure. That shortcut says nothing about the CHB-MIT and Siena test patients and can distort what the model learns.

Without TUSZ, every training subject contributes both preictal and interictal EEG from the same equipment, so the only consistent difference between the classes within a patient is how close a seizure is. TUSZ is used instead as the main false-alarm test in D1, and adding its interictal EEG to training is a D2 experiment (Section 10).

## 7. Thresholds and D1 alarm logic

**Alarm logic (D1).** An alarm is raised when the risk score is at or above the threshold, with no smoothing, after which no new alarm is raised for 30 min (plan, Section 3).

**Threshold (plan, Section 4).** 1,000 evenly spaced candidates from 0 to 1 are tried on the inner validation patients. The chosen threshold is the lowest one whose false alarm rate on those patients is at most 10 per 24 h. False alarms are counted over all time outside preictal and ictal periods, as the plan defines.

## 8. Metrics

As defined in the plan, Section 3.

* **Primary:** the mean of per-patient AUROC (preictal vs interictal windows) across the 25 test patients, each patient counting equally. The AUROC of all test windows pooled is reported alongside it.
* **Three-class results:** the confusion matrix and macro F1.
* **Alarms:** event sensitivity, false alarms per 24 h, time in warning, warning time (including the share of true alarms at least 30 s before onset), and comparison with a random predictor at the same false alarm rate.

Intervals are 95% bootstrap intervals over patients (1,000 resamples, seed 0).

## 9. False-alarm test sets

For TUSZ and mental arithmetic, a "full" model is trained on all CHB-MIT and Siena subjects for each seed, with an inner validation draw for its threshold as in Section 3. It scores every TUSZ interictal window and every mental arithmetic window, and false alarms per 24 h are reported for each dataset, plus the spread across TUSZ patients.

## 10. D2 experiments, fixed in advance

**Reference baseline (added in v1.1).** Every AUROC from D2 on is reported next to a clock-only model: a logistic regression on the sine and cosine of the time of day, trained on the same training patients' preictal and interictal windows and tested on the same folds. In D1 it scored 0.697, higher than the EEG model (D1 finding F-18), so it is the bar a useful EEG model has to beat.

Candidates are tried one at a time, in this order. Each is kept only if it improves the mean inner-validation AUROC across folds; test patients are never used to choose.

1. **Per-patient normalization:** each feature scaled by that recording's median and interquartile range over the preceding 30 min. It uses past data only, so it would work live. Moved first in v1.1, because D1 showed risk scores sitting at very different levels for different patients (F-19).
2. **Context length:** 0, 2, 5 or 10 min of preceding windows, summarized by the mean and slope of each feature over that time.
3. **Time-of-day features (added in v1.1):** the sine and cosine of the clock time, which a live device would know. Part of the time-of-day effect may reflect when hospitals recorded rather than biology, so results are also reported without these features. TUSZ start times are anonymized, so if TUSZ is also kept (item 4), its windows get missing time features, and the dataset check in item 4 is repeated.
4. **TUSZ interictal in training:** on or off, with each patient weighted equally. As a check, I'll also report how well a model can tell which dataset a window came from.
5. **Model family:** gradient boosting (D1) or a small neural network on the per-channel features with the same channel pooling.
6. **Alarm smoothing and persistence:** risk averaged over 1, 6, 12 or 36 windows, and required to stay above threshold for 1, 3 or 6 windows. Chosen to give the highest inner-validation sensitivity with at most 5 false alarms per 24 h.

**How choices are made (v1.2).** Choices are made separately for each test patient's fold, which is stricter than choosing one setup from the average over all folds. An average over folds would include the test patient's own data, because every patient is an inner validation patient in some other folds.

* **Comparing candidates.** In each fold, every candidate is trained on that fold's training patients and scored on its inner validation patients (mean per-patient AUROC), averaged over the five seeds.
* **Keeping a candidate.** A candidate is kept only if it beats the current setup; ties keep the current setup.
* **Using the choice.** The setup chosen for a fold is used only for that fold's test patient. A setup is also chosen the same way on all patients (inner draw as in Section 9), for the false-alarm sets and the final model.
* **Selection fits.** To keep run time reasonable, selection fits use every second window (10 s apart; overlapping windows are highly redundant). Final models use all windows.

**Implementation details (v1.2).**

* **Normalization and context.** Both use the windows ending in the preceding 30 min (normalization) or 2, 5 or 10 min (context) on the same timeline, so they continue across consecutive files. They are computed on the 60 pooled features.
* **Normalization limits.** Normalization needs at least 12 windows (1 min) of history and uses an interquartile-range floor of 0.001. Context slopes are per minute, and missing values are skipped.
* **Time-of-day features.** Only CHB-MIT and Siena recordings placed on a timeline have real clock times. All other windows get missing time features.
* **TUSZ patient split.** TUSZ patients are split in half with seed 0. Only half A can be used for training, with interictal windows taken 30 s apart. Half B is used only for false-alarm testing, so that test always stays on unseen patients.
* **Alarm step.** Smoothing and persistence are chosen per fold by mean inner-validation sensitivity over the seeds, and the threshold is set per seed. The threshold search uses the same 1,000 candidates but a binary search, because it runs many more times than in D1. This assumes the false alarm rate doesn't rise with the threshold, which holds closely but not exactly with a refractory period.
* **Model family (step 5).** The neural network is run after steps 1–4, once PyTorch is installed. If it is kept, the alarm step is repeated.

D2 is compared with D1 on the same folds and seeds (VT-15), using D1's per-patient AUROC for the same seeds. As a robustness check, D2 is also evaluated without the seizures whose annotations were corrected or questioned (D1 findings F-06 and F-08).

## 11. Version history

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-09-26 | Written before any model was trained |
| 1.1 | 2026-09-26 | After the D1 results and before any D2 work: added the clock-only reference baseline and time-of-day features, and moved per-patient normalization to first, based on D1 findings F-18 and F-19. Nothing about D1 changed |
| 1.2 | 2026-09-26 | Before any D2 result: choices made per fold (nested) instead of averaged over folds; implementation details for normalization, context, time-of-day features, the TUSZ patient split and the alarm step; selection fits on every second window; binary threshold search in D2 |

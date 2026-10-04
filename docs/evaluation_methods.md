# Evaluation Methods

| Doc | Version | Author | Written |
|---|---|---|---|
| EVM-001 | 1.22 | Kevin Kim | v1.0 before any model was trained; v1.1 and v1.2 after D1, before any D2 result; v1.3 after a one-seed D2 preview; v1.4 after the full D2 run; v1.5 after the personalized variants; v1.6 while the v1.5 test was running, before any v1.6 result; v1.7 before the lockbox audit; v1.8 and v1.9 after it; v1.10 before the final development round; v1.11 before splitting SeizeIT2; v1.12 during the final development round; v1.13 freezes the design; v1.14 is an erratum; v1.15 adds the sensitivity analysis and SeizeIT2 adapter details; v1.16 the dry-run and lockbox commands; v1.17 fixes the lockbox protocol before the lockbox is opened; v1.18 records the lockbox AUROC result and changes the alarm part before any alarm result was seen; v1.19 adds the continuous-personalization simulation before running it; v1.20 starts v3 development with adaptive thresholds; v1.21 records that result and adds the false-alarm breakdown; v1.22 adopts the v3 scope and adds the first Phase A experiment (see Section 13) |

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
5. **Model family:** gradient boosting (D1) or a small neural network on the per-channel features with the same channel pooling. The network is specified in advance and not tuned (v1.3):
   * **Architecture.** Each derivation's 15 features pass through a shared layer (15→32, ReLU, 32→32, ReLU). The result is pooled over the derivations present by mean and max, and joined with the setup's other features (context and time of day), each with a flag for when it is missing. Then a layer of 64 (ReLU, dropout 0.2) leads to the 3 classes.
   * **Training.** Weighted cross-entropy with the same sample weights as D1, AdamW (learning rate 0.001, weight decay 0.0001), batches of 1,024, 6 epochs, and seeded initialization and shuffling.
   * **Normalization.** When normalization is on, the same causal 30 min rule is applied to each channel's features before pooling.
   * **Implementation.** NumPy (`src/preictal/models/nn.py`), so runs are exactly reproducible; its gradients are checked numerically in `tests/test_nn.py`.
6. **Alarm smoothing and persistence:** risk averaged over 1, 6, 12 or 36 windows, and required to stay above threshold for 1, 3 or 6 windows. Chosen to give the highest inner-validation sensitivity with at most 5 false alarms per 24 h.

**How choices are made (v1.2).** Choices are made separately for each test patient's fold, which is stricter than choosing one setup from the average over all folds. An average over folds would include the test patient's own data, because every patient is an inner validation patient in some other folds.

* **Comparing candidates.** In each fold, every candidate is trained on that fold's training patients and scored on its inner validation patients (mean per-patient AUROC), averaged over the five seeds.
* **Keeping a candidate.** A candidate is kept only if it beats the current setup; ties keep the current setup.
* **Using the choice.** The setup chosen for a fold is used only for that fold's test patient. A setup is also chosen the same way on all patients (inner draw as in Section 9), for the false-alarm sets and the final model.
* **Selection fits.** To keep run time reasonable, selection fits use every third window (15 s apart; overlapping windows are highly redundant). This was every second window in v1.2, changed in v1.3 after the one-seed preview took 106 min. Final models use all windows.

**Implementation details (v1.2).**

* **Normalization and context.** Both use the windows ending in the preceding 30 min (normalization) or 2, 5 or 10 min (context) on the same timeline, so they continue across consecutive files. They are computed on the 60 pooled features.
* **Normalization limits.** Normalization needs at least 12 windows (1 min) of history and uses an interquartile-range floor of 0.001. Context slopes are per minute, and missing values are skipped.
* **Time-of-day features.** Only CHB-MIT and Siena recordings placed on a timeline have real clock times. All other windows get missing time features.
* **TUSZ patient split.** TUSZ patients are split in half with seed 0. Only half A can be used for training, with interictal windows taken 30 s apart. Half B is used only for false-alarm testing, so that test always stays on unseen patients.
* **Alarm step.** Smoothing and persistence are chosen per fold by mean inner-validation sensitivity over the seeds, and the threshold is set per seed. The threshold search uses the same 1,000 candidates but a binary search, because it runs many more times than in D1. This assumes the false alarm rate doesn't rise with the threshold, which holds closely but not exactly with a refractory period.
* **False-alarm sets and the time of day (v1.3).** TUSZ and mental arithmetic have no real clock time. If the setup chosen on all patients uses time-of-day features, a model with the same setup minus those features is trained, with its own threshold and the same alarm smoothing and persistence, and that model is scored on these sets. Otherwise, a missing time can simply switch alarms off, as happened in the preview (0.00 false alarms per 24 h).

D2 is compared with D1 on the same folds and seeds (VT-15), using D1's per-patient AUROC for the same seeds. As a robustness check, D2 is also evaluated without the seizures whose annotations were corrected or questioned (D1 findings F-06 and F-08).

## 11. Patient-specific test (added in v1.3)

This test is a characterization. It doesn't replace or change VT-11 or VT-15, and it has no pass/fail threshold. It asks how well the same pipeline predicts seizures when it has seen the patient before, which is how a wearable would realistically be used.

* **Patients.** CHB-MIT and Siena patients with at least two eligible seizures and at least 1 h of interictal EEG.
* **Folds.** Leave one eligible seizure out at a time (`src/preictal/evaluation/patient_specific.py`).
  * *Test:* that seizure's preictal windows, plus one of n equal chunks of the patient's interictal windows in time order, where n is the number of eligible seizures.
  * *Training:* all other preictal, ictal and interictal windows of the same patient, except anything within 4 h of the held-out seizure's onset and anything within 5 min of the held-out interictal chunk.
* **Model.** The D1 model and features, unchanged, with the D1 sample weights, and seeds 0 to 4.
* **Metrics.**
  * *Per patient:* AUROC over all of the patient's test windows pooled across folds, averaged over seeds.
  * *Overall:* the mean over patients, with a 95% bootstrap interval.
  * *Comparisons:* a patient-specific clock-only model trained on exactly the same windows, and the same patients' cross-patient D1 and D2 results.

### 11.1 Personalized variants (added in v1.4)

This is also a characterization, with no pass/fail threshold. It uses the same 22 patients, the same folds and buffers, and seeds 0 to 4, so every variant is scored on exactly the same test windows as the patient-specific test. Settings are fixed in advance and not tuned (`scripts/run_personalized.py`):

* **This patient only, EEG + time of day:** the D1 features plus the sine and cosine of the time of day.
* **This patient only, EEG + 10 min context + time of day:** as above, plus the 10 min context of the D1 features (mean and slope). 10 min was the context length D2 chose most often.
* **Other patients only, EEG + time of day:** trained on every other CHB-MIT and Siena patient, never on this one; this is D2's setup chosen on all patients. It is trained once per patient and seed, and scored on each fold's test windows.
* **Other patients + this patient, EEG + time of day:** the same, plus this patient's training windows for the fold. Within each class, the patient's own windows carry half of the total weight, and the other patients share the other half as in D1.

Other patients' windows are taken 30 s apart (non-overlapping) to keep the run time reasonable; the patient's own windows are all used. Results are reported as the mean per-patient AUROC with a 95% bootstrap interval. They are compared with the patient-specific EEG and clock-only results, using paired Wilcoxon tests and the number of patients where each variant is higher.

Two risks are stated in advance. With only a few seizures per patient, a patient-only model may learn the clock times of the training seizures rather than a daily pattern, so the time-of-day variants could do worse, not better. And a model trained partly on other patients may lean on the time-of-day pattern that works across patients.

### 11.2 Alarm-level test of the personalized designs (added in v1.5)

This is a characterization, with no pass/fail threshold. It measures what share of seizures the personalized designs would warn about, and how many false alarms they would raise, when the alarm threshold is chosen from each patient's training data only (`scripts/run_personalized_alarms.py`). It uses the same patients, folds, buffers and seeds as Sections 11 and 11.1.

* **Variants:**
  * other patients only, EEG + time of day;
  * other patients + this patient, EEG + time of day;
  * this patient only, EEG + 10 min context + time of day.
* **Threshold.** Within each fold, the training data's interictal windows are split into 3 chunks in time order. Each chunk is scored by a model trained on the rest of the fold's training data, excluding anything within 5 min of the chunk. For the other-patients-only model, which never sees this patient, the training windows are simply scored. The threshold is the lowest of 1,000 candidates, found by binary search, whose false alarm rate on these out-of-sample scores is at most the target. The targets are 5 per 24 h (the D2 target) and 1 per 24 h.
* **Alarm settings.** Fixed to the D2 settings chosen on all patients: risk averaged over 36 windows, above threshold for 6 windows in a row, and a 30 min refractory period.
* **Warned seizures.** The held-out seizure's timeline is scored from 35 min to 5 s before onset, which gives smoothing 5 min to warm up. The seizure counts as warned if an alarm falls 5 s to 30 min before onset.
* **False alarms.** Every alarm on the held-out interictal chunk is a false alarm, and the rate is false alarms over that chunk's hours.
* **Reporting.** Sensitivity, false alarms per 24 h and the chance comparison are pooled over patients for each seed and averaged over seeds. The report also gives the number of patients with at least one seizure warned, and per-patient results.

### 11.3 Feature set v2 and a personal baseline (added in v1.6)

This is a characterization, with no pass/fail threshold. It uses the same patients, folds, buffers and seeds as Section 11.1, and settings fixed in advance (`scripts/run_personalized.py --feature-set v2`).

* **Feature set v2** (`src/preictal/features/build_features.py`, version `d2-v2`):
  * *Per derivation:* D1's 15 features plus 4 more: spectral entropy, peak frequency, log(theta/alpha) and log((delta+theta)/(alpha+beta)), pooled by mean, standard deviation, minimum and maximum as in D1 (76).
  * *Connectivity (12):* for 1–40, 4–8 and 13–30 Hz (causal 4th-order Butterworth filters, with 10 s of warm-up where the recording allows), the correlation matrix of the present derivations over each window gives four numbers. They are the mean absolute correlation, the largest eigenvalue as a fraction of the number of channels, the normalized entropy of the eigenvalues, and the mean absolute correlation between left-right homologous derivations.
  * *In total:* 88 EEG features, plus the time of day. Extracted with `scripts/extract_features.py --feature-set v2` into `data/processed/features_v2/`; the v1 features are unchanged.
* **Personal baseline.** Each patient's EEG features (not the time of day) are scaled by the median and interquartile range of their own interictal windows (floor 0.001). For the test patient, only the fold's training interictal windows are used; other patients use all their interictal windows. It needs no seizures, so a device could learn it from its wearer's first days of normal EEG.
* **Variants.** Other patients only, and other patients + this patient (half the weight), each with feature set v2 and each without and with the personal baseline: four results.
* **Without the time of day (added in v1.8).** The lockbox audit (Section 12) found that SeizeIT2's EEG files all start at 00:00:00, so its clock times are anonymized and the design tested there can't use the time of day. The two personal-baseline variants are therefore also run without time-of-day features (`--no-clock`), so their performance on CHB-MIT and Siena is known before the design is frozen. Each is compared per patient with the same design using feature set v1 (Section 11.1), by Wilcoxon test and the number of patients where it is higher.
* **Risks stated in advance:**
  * more features give the patient-specific part more room to overfit a few seizures;
  * scaling to a baseline may remove differences between states (for example sleep and wake) that carry information;
  * with 22 patients, real gains of a few hundredths may not be distinguishable from noise.

### 11.4 Final development round (added in v1.10)

CHB-MIT and Siena now serve as the development set and SeizeIT2 as the sealed test set (Section 12). This round picks the design to freeze.

* **Base design:** other patients + this patient, feature set v2, personal baseline, no time of day (AUROC 0.681 in Section 11.3). It doesn't use the time of day because SeizeIT2 can't.
* **Four challengers,** each changing one thing (`scripts/run_personalized.py`):
  1. a 10 min context: the mean and slope of each feature over the preceding 10 min, scaled by the personal baseline like the other features;
  2. a 30 min context;
  3. a personal share of 0.75, so the patient's own windows carry three quarters of each class's weight;
  4. more cautious trees: minimum leaf size 200, at most 15 leaves per tree, L2 regularization 1.0.
* **Evaluation.** Same 22 patients, folds, buffers and seeds as Section 11.1. Each challenger is compared per patient with the base design.
* **Selection rule, fixed now.** The design to freeze is the base design, unless a challenger's mean AUROC is at least 0.01 higher; if several are, the highest. Combinations of challengers aren't tested, to keep the number of choices small. The choice is made on these 22 patients, so the chosen design's score here is slightly optimistic; the lockbox gives the unbiased estimate.
* **Challenger 5 (added in v1.12): training with a 1-hour gap.** This is the base design with every training window labeled using a 1 h interictal gap instead of 4 h (`--train-gap-h 1`), so EEG 1–4 h from a seizure is used as normal for training. That covers the patient's and the other patients' training windows, and the windows used for the personal baseline. Testing is unchanged: the held-out interictal chunks are the 4 h interictal windows, nothing within 4 h of the held-out seizure is trained on, and the same 22 patients are tested. The aim is more training data, especially from Siena, without making the test easier.
* **Combination step (v1.12).** If two or more challengers qualify, the two best are combined in one more run, and the design frozen is the highest-scoring among the qualifying challengers and that combination. This step was added after challengers 1–3 were seen (10 min context 0.700 qualifies; 30 min context 0.654 and personal share 0.75 at 0.688 don't), and before the results of challengers 4 and 5.

### 11.5 Frozen design (v1.13, 2026-09-30)

**Selection.** The rule in Section 11.4 was applied to the final development round (base design 0.681):

| Challenger | Mean AUROC | Beat the base in |
|---|---|---|
| 10 min context | 0.700 | 11 of 22 |
| 30 min context | 0.654 | 12 of 22 |
| personal share 0.75 | 0.688 | 15 of 22 |
| more cautious trees | 0.677 | 11 of 22 |
| trained with a 1 h gap | 0.684 | 11 of 22 |

Only the 10 min context is at least 0.01 above the base, so there is no combination step. The frozen design is the base design with 10 min context. Its development score, AUROC 0.700 (95% CI 0.630–0.768) on 22 patients, is optimistic, because it was chosen on those patients. It improved only 11 of 22 patients, so the gain may not hold on new data.

**The frozen design.** Nothing below may change after this point.

* **Labels:** as in the verification plan.
  * *Before seizure:* 30 min to 5 s before onset.
  * *Normal:* at least 4 h from any seizure.
  * *Seizure grouping:* seizures less than 30 min apart form one event.
  * *Eligibility:* an event is eligible if at least 90% of its preictal period is recorded.
  * *Windows:* 30 s long, every 5 s.
* **Features:** feature set v2 (Section 11.3: 76 pooled per-derivation features and 12 connectivity features), plus the mean and slope over the preceding 10 min of each (Section 10), giving 264 columns. No time of day.
* **Personal baseline:** every column minus its median, divided by its interquartile range (floor 0.001), over reference windows. For the person being predicted, the references are their own interictal training windows; each model uses only the windows it was trained on. For other patients, the references are all their interictal windows.
* **Model:** scikit-learn `HistGradientBoostingClassifier` with default settings and `random_state` equal to the seed. Three classes; the risk is the probability of preictal.
* **Training data:**
  * *Other patients:* their preictal, ictal and interictal windows, taken 30 s apart, weighted as in D1 (each class equal, each patient equal within a class).
  * *The person:* their own training windows, which carry half of each class's weight.
* **Alarms:**
  * *Rules:* the risk averaged over 36 windows (3 min), above threshold for 6 windows in a row (30 s), then a 30 min refractory period.
  * *Threshold:* the lowest of 1,000 candidates (binary search) whose false alarm rate is at most the target (5 and 1 per 24 h). It is measured on out-of-sample scores of the person's own training interictal windows: 3 chunks, each scored by a model trained without it and with a 5 min gap around it.
* **Personalized evaluation (Section 11):**
  * *Folds:* leave one eligible seizure out at a time; the test is that seizure's preictal windows and one of n interictal chunks.
  * *Buffers:* nothing within 4 h of the held-out seizure, or within 5 min of the held-out chunk, is used for training.
  * *Patients:* those with at least 2 eligible seizures and at least 1 h of interictal windows.
  * *Seeds:* 0 to 4.

**Applying it to SeizeIT2 (the lockbox).**

* **Channels:** the behind-the-ear EEG channels present (`BTEleft SD`, `BTEright SD`, `CROSStop SD`), resampled to 256 Hz where a file uses another rate (erratum, v1.21: the text said "from 250 Hz", but files can already be at 256 Hz; the code resamples from each file's own rate), are the "derivations". Features are pooled over the channels present. For connectivity, `BTEleft SD` and `BTEright SD` form the left-right homologous pair when both are present.
* **Seizures:** annotation rows whose `eventType` starts with `sz` are seizures (onset and duration from the file). Other rows are ignored.
* **Timeline:** clock times are anonymized, so each patient's files are placed back to back in run-number order. Distances used for the 4 h normal-EEG rule are measured on this timeline; real breaks between files can only make true distances longer, so normal EEG stays at least 4 h from any seizure. Preictal windows come only from the same file as their seizure, and the 90% rule is applied within that file.
* **Other patients** for the general part are all other SeizeIT2 patients (development and lockbox), never the test patient. Everything else is as above.
* **What may still change:** only technical adapter code (loading, channel mapping, the timeline rule above), written and checked on the 25 development patients. The design does not change, and lockbox data is not used before the lockbox run.

**Planned next, in this order:**

1. **Alarm-level test of the frozen design on CHB-MIT and Siena** (`scripts/run_personalized_alarms.py --frozen`), with the same folds and targets as Section 11.2. It uses seeds 0 and 1 only, because each seed takes several hours with 264 features and the seed changes little (D2's spread across seeds was ±0.007).
2. **1 h sensitivity analysis** on CHB-MIT and Siena: the frozen design with every label, for training and testing, using a 1 h gap, on the patients eligible under that definition.
3. **SeizeIT2 adapter,** built and checked on the 25 development patients, including how many seizures have their preictal period inside their own file.
4. **The lockbox run,** once, on the 100 lockbox patients.

**Erratum (v1.14, 2026-09-30).** While writing a plotting script after the freeze, it turned out that the list of left-right homologous pairs in feature set v2 spells the frontopolar derivations "FP1"/"FP2", while the derivation names are "Fp1"/"Fp2". Those two pairs (Fp1-F7/Fp2-F8 and Fp1-F3/Fp2-F4) never matched. So the homologous-correlation connectivity feature (1 of the 4 connectivity measures, in each of the 3 bands) was computed from the other 6 pairs, in every v2 result. The frozen design is kept exactly as it was developed and evaluated, so the lockbox runs the same code. The behaviour is documented in the code and pinned by a test. For SeizeIT2, the homologous pair is specified separately (`BTEleft SD` with `BTEright SD`) and is unaffected.

### 11.6 After the freeze: sensitivity analysis and the SeizeIT2 adapter (v1.15)

Neither changes the frozen design.

**1 h sensitivity analysis.** This is the frozen design (general + personal, feature set v2, personal baseline, 10 min context, no time of day) with every window, for training and testing, labeled using a 1 h interictal gap (`scripts/run_personalized.py --test-gap-h 1`).

* **Patients:** those with at least 2 eligible seizures and 1 h of interictal windows under 1 h labels.
* **Buffer:** the buffer around the held-out seizure is 1 h, the same as the gap; the 5 min buffer around the held-out interictal chunk is unchanged.
* **Seeds:** 0 to 4. The result is the mean per-patient AUROC.
* **Comparison:** per patient with the frozen design's 4 h result (`personalized_dev_ctx10`), for the patients in both.
* **Reporting:** alongside the 4 h results, never instead of them.

**SeizeIT2 adapter** (`src/preictal/data/seizeit2.py`, `scripts/extract_seizeit2.py`, tested in `tests/test_seizeit2.py`). These are technical details of the rules in Section 11.5:

* **Files:** each subject's `ses-*/eeg/*_eeg.edf` files are ordered by session and run number from the file names, and the seizures are read from the matching `_events.tsv`.
* **Signals:** the channels are matched by exact label and converted to µV using the EDF physical units. They are resampled from each file's own rate to 256 Hz (unchanged if it is already 256 Hz) with the same polyphase resampler as the other datasets, read in 1 h pieces with 2 s of padding and 10 s of filter warm-up, as in feature set v2. A channel that's absent is left out of pooling, as elsewhere.
* **Features:** the feature version is `d2-v2-bte`. Features go to `data/processed/features_seizeit2/`, with timeline keys `seizeit2|sub-XXX`.
* **Lockbox guard:** the extraction script refuses lockbox patients unless it is given `--lockbox-run` and the `freeze-v1.13` Git tag exists.
* **Development patients:** a feasibility report (`results/seizeit2_dev/feasibility.md`) counts, per development patient, seizures, eligible events, preictal and interictal hours, and whether the patient qualifies for the personalized test.
* **Next, a dry run:** the frozen design is run on the development patients only, as a check that the full pipeline works on SeizeIT2. Its general part uses the other development patients. It is reported as development, never as the lockbox result.

**Development feasibility (2026-09-30).** The 25 development patients have 538 EEG files. They contain 204 seizures in 169 events, of which 154 are eligible, with the preictal period inside the seizure's own file. There are 76.7 h of preictal and 1,719.9 h of interictal windows. 16 of the 25 patients qualify for the personalized test.

**Dry run and lockbox commands (v1.16).** `scripts/run_personalized.py` and `scripts/run_personalized_alarms.py` take `--dataset seizeit2 --group development`. This runs the frozen design (general + personal, feature set v2, personal baseline, 10 min context, no time of day, plus the frozen alarm settings) on the development patients, with the general part trained on the other development patients.

* **The dry run** uses seed 0 only. It checks that the pipeline works end to end and measures run time; its numbers are reported as development results.
* **For the lockbox run,** the same commands take `--group lockbox --lockbox-run`, which the scripts refuse without the `freeze-v1.13` tag. The general part is trained on all other SeizeIT2 patients.
* **Lockbox seeds:** the seeds for the lockbox run will be fixed from the dry run's measured run time, and written here before the lockbox run, never after seeing lockbox results.

**Dry run (2026-09-30, development patients, seed 0).** 14 patients qualified.

* **AUROC:** the frozen design scored 0.669 (95% CI 0.585–0.743), against 0.516 (0.409–0.602) for other patients only. Adding the patient's own data helped in 13 of 14 patients.
* **Alarms, target ≤ 5 per 24 h:** the frozen design warned 46% of seizures at 4.58 false alarms per 24 h (chance 9%).
* **Alarms, target ≤ 1 per 24 h:** it warned 20% at 1.71 per 24 h (chance 3.5%).
* **Other patients only:** alarms were at chance level.

The alarm part took about 2.3 h.

### 11.7 Lockbox protocol (v1.17, fixed before the lockbox is opened)

* **Seeds:** seed 0 only, for both the AUROC part and the alarm part. Scaled from the dry run, the lockbox (about 60 or more qualifying patients, with all 125 patients in the training pool) takes about 12–15 h per seed for the AUROC part and about 2 days per seed for the alarm part. Seeds have changed results by about ±0.007 throughout.
* **Runner:** `scripts/run_seizeit2.py`. It does the same computations as the dry-run scripts, restructured to fit in memory: context is computed one patient at a time, and only the other patients' training rows are kept. It saves progress after every patient, so an interrupted run resumes.
* **Check before opening the lockbox:** `--check` reruns chosen development patients and must report identical results to the dry run ("CHECK PASSED") before the lockbox is opened.
* **Order:**
  1. extract the lockbox features (`scripts/extract_seizeit2.py --group lockbox --lockbox-run`);
  2. the AUROC part;
  3. the alarm part.
* **Reporting:** results are reported whatever they are, with nothing changed after seeing them. The protocol commit is tagged `lockbox-protocol-v1.17` before the lockbox is opened.

### 11.8 Lockbox AUROC result, the check, and the alarm part (v1.18, 2026-10-02)

**AUROC part (seed 0), completed 2026-10-01.** 67 lockbox patients qualified, and 62 had at least one usable fold.

* **The frozen design:** mean per-patient AUROC 0.621 (95% CI 0.564–0.671).
* **Other patients only:** 0.547 (0.510–0.583).
* **Adding the patient's own data** helped in 38 of 62 patients.

These are the lockbox AUROC results and are reported as they are.

**The equivalence check.** Two things differ from v1.17's plan:

* **The check came after the AUROC part.** It was run after the lockbox AUROC part, not before the lockbox was opened.
* **The first attempt compared nothing.** The patient IDs were passed as one shell argument (zsh doesn't split `$SUBS`), so no patient qualified, but the runner still printed "CHECK PASSED". That was a bug. The runner now splits the IDs and fails if any given patient doesn't qualify, or if nothing is compared.

The real check, on development patients sub-001 and sub-002, reproduced all 12 dry-run results exactly (both parts), confirming that the lockbox runner computes the same as the dry-run scripts.

**Alarm part.** After 10 h it had finished 3 of 62 patients (about 3.3 h each), so all 62 would take about 8 more days on the laptop. The protocol is therefore changed as follows, decided before anyone looked at the 3 finished alarm results:

* the alarm part runs on **20 patients drawn at random** (seed 0, `--subset 20`) from the 62 scored in the AUROC part, using only their IDs;
* any of the 3 finished patients that are drawn are kept; the others are left out of the report;
* the method is otherwise unchanged, and the report lists the 20 patients.

### 11.9 Continuous personalization, simulated forward in time (v1.19)

This is a characterization. It asks how prediction improves as a device keeps learning its wearer. The frozen recipe is re-run as a device would run it, strictly forward in time, on the 25 SeizeIT2 development patients (seed 0; `scripts/run_learning_curve.py`, step logic in `src/preictal/evaluation/learning_curve.py` and tested in `tests/test_learning_curve.py`).

* **Calibration (step 0).** This is the first 6 h of recording, or up to 30 min before the first eligible seizure if that comes sooner. It must be at least 1 h, otherwise there is no step 0. The personal baseline comes from all non-ictal windows in it, which the device assumes are normal. The device then predicts with the general model until the first seizure.
* **Retraining (step k).** The device retrains 1 h after the onset of the k-th eligible seizure, using only what it could know by then:
  * preictal and ictal windows of seizures that have already happened;
  * interictal windows ending at least 4 h before the retraining time, since only then can they be confirmed as normal.

  The personal baseline comes from those interictal windows. The model is the frozen recipe: other patients plus this patient's windows with half of each class's weight, feature set v2, 10 min context, no time of day.
* **General part.** It is trained on the other development patients only, so the lockbox patients aren't used and run time stays at a few hours.
* **Scoring.** Each step is scored from its retraining time until the next eligible seizure, never on anything it was trained on.
  * *AUROC:* that seizure's preictal windows against the interictal windows in between.
  * *Alarms:* the frozen settings (36-window smoothing, persistence 6, 30 min refractory, targets 5 and 1 per 24 h). The threshold comes from what the device knew: at step 0, and for the comparison model, from its own training-period windows; for the learning device, from 3 inner chunks of its interictal training windows, as frozen. The next seizure counts as warned if an alarm falls 5 s to 30 min before it.
* **Comparison.** At every step, the general model with the same updated personal baseline, which never learns seizures, is scored too.
* **Reporting.** Results are given by the number of seizures learned (0, 1, 2, 3, 4, 5 or more): mean AUROC over steps with a 95% bootstrap interval, alarms pooled, and a learning-curve figure.
  * *Skipped steps:* a step is skipped when the next seizure comes before retraining; steps with no interictal windows in their test period have no AUROC.
* **Interpretation.** Later points come only from patients with many seizures, so they describe those patients, not everyone.
* **When it runs:** after the lockbox alarm part has finished.

### 11.10 v3 development: adaptive alarm thresholds (v1.20)

**Status of v3.** The SeizeIT2 lockbox has been used for v2's final test, so it can no longer give an untouched estimate. Every v3 result is a development result, labeled that way, and none of them changes v2's reported results. A fresh final test for v3 would need new data.

**Why adaptive thresholds.** The main failure in the lockbox and in the forward-in-time simulation was that false alarms exceeded their targets: 5.8 per 24 h against 5 on the lockbox, and 13.8 in the simulation. A threshold set once, at retraining, doesn't follow the wearer's changing EEG.

**Method.** This uses the simulation of Section 11.9 (`scripts/run_learning_curve.py --adaptive --tag _adaptive`), with the same models, seed 0 and patients. Each step's alarms are evaluated twice:

* **Fixed:** the threshold set at retraining, as in v1.19.
* **Adaptive:** the threshold is recalibrated every 6 h after retraining, with the same rule as at retraining (the lowest of 1,000 candidates with a false-alarm rate at most the target). It is recalibrated on the model's scores for the wearer's recent confirmed-normal EEG:
  * *Which EEG:* interictal windows from the 24 h ending 4 h before recalibration, and only after the last retraining, so the model was never trained on them.
  * *Minimum:* if there are fewer than 2 h of them, the previous threshold is kept.
  * *Before the first recalibration,* the threshold from retraining is used.

Both models (the learning device and the never-learning comparison) and both targets (5 and 1 per 24 h) are evaluated. The AUROC results are recomputed and must match the v1.19 run exactly, which checks that the run is reproducible.

**Decision rule, fixed in advance.** The primary comparison is the learning device at the ≤ 5 target, over all steps after at least one learned seizure. Adaptive thresholds count as an improvement if:

* the false-alarm rate is closer to the target than with the fixed threshold (or at or below it), and
* the share of seizures warned still beats chance (p < 0.05).

The ≤ 1 target and the never-learning model are reported as secondary results.

**Result (2026-10-03).** The AUROC results and the fixed-threshold alarms reproduced the v1.19 run exactly. Over the 95 seizures after at least one learned seizure, for the learning device:

| Thresholds | Target | Warned | False alarms per 24 h | Chance | p |
|---|---|---|---|---|---|
| Fixed | ≤ 5 | 36/95 (38%) | 13.77 | 0.249 | 0.0034 |
| Adaptive | ≤ 5 | 33/95 (35%) | 10.24 | 0.192 | 0.00026 |
| Fixed | ≤ 1 | 22/95 (23%) | 9.18 | 0.174 | 0.091 |
| Adaptive | ≤ 1 | 23/95 (24%) | 6.00 | 0.117 | 0.00052 |

**Decision.** By the decision rule, adaptive thresholds count as an improvement: false alarms came closer to the target (10.24 against 13.77, target 5) while warnings still beat chance. The never-learning model gained nothing (16% against 14% warned, both at chance). False alarms remain well above both targets.

### 11.11 v3 development: false-alarm breakdown (v1.21)

**Status.** This is a diagnostic, not a verification test. It describes where false alarms come from in the forward-in-time simulation (Sections 11.9 and 11.10), and changes no model, threshold or alarm rule. Any change it motivates needs its own written plan, added to this document before it is run.

**What is logged.** The simulation is rerun with `--adaptive --log-alarms --tag _breakdown` (same seed, same models; its counts must equal the earlier run's). Every alarm is written to `results/seizeit2_dev/alarm_log_breakdown.csv`: true and false alarms, under fixed and adaptive thresholds, for both models and both targets (≤ 5 and ≤ 1 per 24 h). For each alarm it records:

* **Learning stage:** hours since monitoring started, seizures learned so far, hours since the last retraining, and hours since the last threshold recalibration.
* **Patient:** the subject ID, the file and the time within it, to see whether a few patients produce most of the false alarms.
* **Signal quality** in the 5 min before the alarm, computed afterwards by `scripts/breakdown_false_alarms.py`:
  * *movement:* the variability of the accelerometer magnitude, from SeizeIT2's `mov` recording of the same run;
  * *muscle:* the EMG RMS above 20 Hz, from the `emg` recording;
  * *EEG muscle index:* 30–45 Hz power on the behind-the-ear channels, which is always available.

  The `mov` and `emg` files are assumed to share the EEG file's start and timing (the same run). A measure that can't be read is left out and counted.
* **Clock time:** not available, since SeizeIT2's times are anonymized (F2-14).

**What is reported.**

1. False alarms per 24 h by learning stage (1, 2, 3, 4, or 5 or more seizures learned) and by time since retraining (0–6 h, 6–24 h, more than 24 h).
2. The share of false alarms from the 3 patients with the most, and per-patient false-alarm rates.
3. For each measure, the share of false alarms during high activity, meaning above the same patient's 90th percentile in 150 randomly sampled normal-EEG windows (seed 0). That compares with the 10% expected by chance (one-sided binomial test).
4. All of the above side by side for fixed and adaptive thresholds, with a check that the logged false alarms equal the simulation's own counts.

**Candidate follow-up experiments.** Each needs its own amendment and decision rule before it is run:

* **Warm-up:** no personal-model alarms until a minimum amount of confirmed-normal EEG has been seen, with a stricter threshold until then.
* **Artifact gating:** windows with high movement or muscle activity can't contribute to an alarm.
* **Stricter persistence:** a longer time above threshold before an alarm fires, reported with its cost in warned seizures.
* **Personal time prior:** a record of when this person's own seizures occur, combined with the EEG risk score. CHB-MIT and Siena only, since SeizeIT2 has no clock. It must be compared against a personal clock-only model.

All results are reported as seizures warned at ≤ 1 and ≤ 5 false alarms per 24 h, against random alarms at the same rate, and labeled as v3 development results.

### 11.12 v3 scope, and Phase A experiment 1: threshold schedules (v1.22)

**Scope.** v3 is a personalized, adaptive algorithm (`docs/v3_scope.md`). Its success criteria (S1 to S3) and data plan are fixed there, before any v3 evaluation on held-out patients:

* *Phase A:* tune on the 25 SeizeIT2 development patients;
* *Phase B:* evaluate once on the other 100.

**Why this experiment.** The breakdown (F3-02) found that, with adaptive thresholds, the remaining false alarms concentrate in the first 24 h after each retraining (9.6 and 12.3 per 24 h, against 3.4 later). Recalibration can't act sooner because it waits for 4 h of confirmed normal EEG, then needs 2 h of it.

**Method.** This uses the simulation of Section 11.9 (`scripts/run_learning_curve.py --adaptive --arms --tag _arms`), with the same models, seed 0 and the 25 development patients. Four threshold schedules are evaluated on the same models:

* **`adaptive`:** as in v1.20 (every 6 h; interictal windows ending at least 4 h before; at least 2 h of them; the last 24 h). It must reproduce the v1.20 numbers.
* **`fast`:** recalibrate every 1 h on any non-seizure windows (interictal or excluded) recorded since retraining that ended at least 1 h before (at most the last 24 h, at least 1 h of them), with the same threshold rule. One hour after its end, a window can no longer be preictal for an upcoming seizure. If preictal-like EEG slips in, the threshold only gets stricter.
* **`strict24`** (≤ 5 setting only): `adaptive`, but for the first 24 h after each retraining it uses the stricter (higher) of that step's ≤ 5 and ≤ 1 thresholds.
* **`fast_strict24`** (≤ 5 setting only): the same, built on `fast`.

**Decision rule, fixed in advance.** For the learning device at the ≤ 5 setting, over steps after at least one learned seizure, the chosen schedule is the arm with the lowest observed false-alarm rate, among the arms whose:

* warned share beats chance (one-sided binomial, p < 0.05), and
* warned share is no more than 5 percentage points below `adaptive`'s.

If no other arm qualifies, `adaptive` is kept. The chosen schedule becomes part of the configuration taken to Phase B.

## 12. Lockbox: SeizeIT2 (added in v1.7)

SeizeIT2 v1.1.0 (OpenNeuro ds005873, CC0 licence) was downloaded on 2026-09-28 into `data/raw/seizeit2_v1.1.0/`: 24,877 files, 117.2 GiB. It has 125 patients with focal epilepsy, behind-the-ear EEG and other wearable signals. It is kept sealed until the final design is frozen, so it can give one unbiased test of that design.

**Allowed before the design is frozen:**

* file counts and sizes;
* `dataset_description.json` and `CHANGES`, to confirm the version;
* the blind feasibility audit (`scripts/audit_seizeit2.py`). It reads only file listings, EDF headers (channel names, sampling rates, durations and start times), and the column names and event categories of the annotation files. It reports seizure numbers only as totals across the whole dataset. Its report, `results/lockbox/seizeit2_feasibility.md`, is committed as a record of what was looked at.
* since v1.8, the recording start times in the BIDS `scans.tsv` files and the gaps between consecutive EEG recordings. This is recording timing only, nothing about seizures, and it decides whether recordings can be placed on one timeline.
* since v1.9, the `dateTime` and `recordingDuration` columns of the annotation files. They are used only if every row of a file carries the same `dateTime`, which makes it the recording's start time rather than an event's. Otherwise they are counted and not used, and no time is printed. Only totals, and the gaps between consecutive recordings, are reported.

**What the first audit found (2026-09-28).**

* **Coverage:** 125 subjects and 11,009 EDF files, all readable. EEG is in 2,850 files (11,626 h) with behind-the-ear channels `BTEleft SD`, `BTEright SD` and `CROSStop SD`, plus ECG, EMG and movement recordings.
* **Clock times:** every EEG file starts at 00:00:00.
* **Seizures:** 883 in total; 97 subjects have at least two.
* **Recording timing (second run, v1.8):** there are no `scans.tsv` files. All 2,850 annotation files have the columns onset, duration, eventType, lateralization, localization, vigilance, confidence, channels, dateTime and recordingDuration.

**Not allowed before the design is frozen:** reading or plotting EEG samples, computing features, looking at any seizure timing or at any per-patient seizure information, or running any model on the data.

**Development and lockbox split (v1.11).** Before anything beyond the audit is looked at, SeizeIT2 is split once by `scripts/split_seizeit2.py`. It draws 25 of the 125 subject IDs at random (seed 0) for development and leaves the other 100 as the lockbox. It uses only the subject folder names, no seizure or recording information. The split is saved to `configs/seizeit2_split.yaml`, and the script refuses to run again once that file exists.

* **Development patients** may be used to build and debug the behind-the-ear channel adapter and loaders, to check that the pipeline runs end to end, and later for wearable-specific development. They are never part of a lockbox result.
* **Lockbox patients** stay sealed under the rules above.

**Planned use.** Once the design is frozen, and written down here as a new version, the frozen method is applied once to SeizeIT2. The personalized pipeline and its rules stay unchanged, apart from a channel-mapping adapter for the behind-the-ear EEG, which is written using only the audit's header information. It is applied to the 100 lockbox patients. The results are reported whatever they are, and nothing is changed after seeing them.

## 13. Version history

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-09-26 | Written before any model was trained |
| 1.1 | 2026-09-26 | After the D1 results and before any D2 work: added the clock-only reference baseline and time-of-day features, and moved per-patient normalization to first, based on D1 findings F-18 and F-19. Nothing about D1 changed |
| 1.2 | 2026-09-26 | Before any D2 result: choices made per fold (nested) instead of averaged over folds; implementation details for normalization, context, time-of-day features, the TUSZ patient split and the alarm step; selection fits on every second window; binary threshold search in D2 |
| 1.3 | 2026-09-26 | After a one-seed D2 preview (v1.2), which showed cross-patient EEG performance at chance without time-of-day features (0.505; 0.600 with them; clock-only 0.697) and 0.00 false alarms on the false-alarm sets because those recordings have no clock time. Added: the neural network specification (step 5 was already planned), the false-alarm scoring fix, selection fits on every third window, and the patient-specific test (Section 11). The step order and selection rules are unchanged. The preview itself is kept as a record and not reported as the D2 result |
| 1.4 | 2026-09-27 | After the full D2 run (VT-15 and VT-17 failed; the patient-specific test gave 0.662): added the personalized variants (Section 11.1), before running them. Nothing about D1, D2 or the patient-specific test changed |
| 1.5 | 2026-09-27 | After the personalized variants (best: other patients + this patient, AUROC 0.698): added the alarm-level test of the personalized designs (Section 11.2), before running it |
| 1.6 | 2026-09-27 | While the v1.5 test was running and before any v1.6 result: added feature set v2 and the personal baseline (Section 11.3) |
| 1.7 | 2026-09-28 | Before any look at SeizeIT2 beyond file counts and the version files: added the lockbox rules and the blind feasibility audit (Section 12) |
| 1.8 | 2026-09-28 | After the blind audit (anonymized SeizeIT2 clock times; 97 subjects with at least two seizures): added no-time-of-day versions of the personal-baseline variants (Section 11.3) and a recording-timing check to the audit (Section 12), before running either |
| 1.9 | 2026-09-28 | After the second audit run (no `scans.tsv`; annotation files have dateTime and recordingDuration columns): added the recording-timing check from the annotation files (Section 12), before running it |
| 1.10 | 2026-09-29 | After the v1.6 and v1.8 results (best no-clock design 0.681): added the final development round and its selection rule (Section 11.4), before running it |
| 1.11 | 2026-09-29 | Before splitting SeizeIT2: 25 development and 100 lockbox patients, drawn once from subject IDs with seed 0 (Section 12) |
| 1.12 | 2026-09-29 | During the final development round, after challengers 1–3 and before 4 and 5: added challenger 5 (training with a 1 h gap, testing with 4 h) and the combination step (Section 11.4) |
| 1.13 | 2026-09-30 | Final development round complete (challenger 5: 0.684): design frozen as the base design with 10 min context (Section 11.5), including how it is applied to SeizeIT2, and the remaining steps in order |
| 1.14 | 2026-09-30 | Erratum: the frontopolar homologous pairs never matched, so the homologous correlation used 6 of 8 pairs; kept as frozen (Section 11.5) |
| 1.15 | 2026-09-30 | Details of the planned 1 h sensitivity analysis and the SeizeIT2 adapter, including the lockbox guard and the development-patient dry run (Section 11.6); no design change |
| 1.16 | 2026-09-30 | Development feasibility results; dry-run and lockbox commands; lockbox seeds to be fixed from the dry run's run time before the lockbox run (Section 11.6) |
| 1.17 | 2026-10-01 | Dry-run results; lockbox protocol (seed 0 for both parts, memory-efficient runner checked against the dry run, order of steps) fixed before the lockbox is opened (Section 11.7) |
| 1.18 | 2026-10-02 | Lockbox AUROC result; the equivalence check (run after the AUROC part; first attempt compared nothing, runner fixed; real check identical); alarm part reduced to 20 random patients (seed 0) because of run time, before any alarm result was seen (Section 11.8) |
| 1.19 | 2026-10-02 | Added the continuous-personalization simulation, forward in time, on the SeizeIT2 development patients (Section 11.9), before running it |
| 1.20 | 2026-10-03 | v3 development begins (development results only; the lockbox is used). Adaptive alarm thresholds, recalibrated every 6 h on recent confirmed-normal EEG, with a decision rule fixed in advance (Section 11.10) |
| 1.21 | 2026-10-03 | Adaptive-threshold result and decision (an improvement by the pre-set rule); false-alarm breakdown plan (Section 11.11); erratum on SeizeIT2 sampling rates |
| 1.22 | 2026-10-04 | Adopts the v3 scope (`docs/v3_scope.md`: intended use, success criteria S1 to S3, Phase A and Phase B data plan); Phase A experiment 1, threshold schedules, with its decision rule (Section 11.12) |

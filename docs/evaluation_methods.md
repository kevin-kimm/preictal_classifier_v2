# Evaluation Methods

| Doc | Version | Author | Written |
|---|---|---|---|
| EVM-001 | 1.11 | Kevin Kim | v1.0 before any model was trained; v1.1 and v1.2 after D1, before any D2 result; v1.3 after a one-seed D2 preview; v1.4 after the full D2 run; v1.5 after the personalized variants; v1.6 while the v1.5 test was running, before any v1.6 result; v1.7 before the lockbox audit; v1.8 and v1.9 after it; v1.10 before the final development round; v1.11 before splitting SeizeIT2 (see Section 13) |

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

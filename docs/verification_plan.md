# Verification Test Plan: preictal_classifier_v2

| Field | Value |
|---|---|
| Document ID | VTP-001 |
| Version | 0.2 (draft) |
| Status | Draft. Section 2 decisions are resolved. Set the version to 1.0 and commit before running any test in Section 6. |
| Author | Kevin Kim |
| Scope | Deliverables 1, 2 and 3 of the course plan |

## 1. Purpose

This plan states what will be verified, how each test is run, and what counts as a pass or a fail, before any testing begins. Results are recorded against the frozen version of this plan (identified by its Git commit hash) in `docs/verification_results/`. Results for every test are reported, including failures. If the plan has to change after it is frozen, the change is made in a new version with a written reason (Section 8), never by editing criteria to fit a result.

Two kinds of test are used. A **verification** test has a pass/fail criterion. A **characterization** test measures and reports a property without a threshold, because no defensible threshold exists yet; its result informs later targets.

## 2. Decisions

Each item below resolves an ambiguity or open design choice in the course plan. They are fixed when this plan is frozen.

| ID | Question | Resolution |
|---|---|---|
| D-1 | Where does the preictal period end? Earlier wording gave both 30 s and 5 s. | 5 s before onset (confirmed by the author). The preictal period runs from 30 min to 5 s before onset. |
| D-2 | Is the Deliverable 2 improvement of at least 15% relative or absolute, and on which metric? | Relative improvement in mean cross-patient AUROC (preictal vs interictal) over Deliverable 1, on the same folds and seeds (confirmed by the author). Example: 0.65 in D1 requires at least 0.7475 in D2. |
| D-3 | What is the Deliverable 2 event-level target? | Event sensitivity of at least 80% with no more than 5 false alarms per 24 h (confirmed by the author). This is in the range reported by patient-specific studies; cross-patient results are usually lower, so a fail is plausible and must be reported rather than tuned away. |
| D-4 | Which common signal representation is used? CHB-MIT is recorded as bipolar pairs, so referential channels cannot be recovered from it. | The 18-derivation bipolar longitudinal montage ("double banana") with modern 10-20 names, listed below. CHB-MIT already uses these derivations. Siena, TUSZ and the Cyton record referential signals and are converted by subtracting electrode pairs. Subtraction cancels the reference electrode, so recordings referenced to the average, to linked ears, or to the Cyton's SRB electrode become directly comparable. Derivations with a missing electrode are marked absent, never filled in; the model is montage-agnostic. |
| D-5 | What counts as interictal in TUSZ, where many sessions are short and the time between sessions is not known precisely? | For TUSZ patients with at least one annotated seizure, sessions with no seizure count as interictal. In sessions that contain a seizure, no window counts as interictal unless file start times show it is at least 4 h from every seizure in the session. TUSZ patients with no annotated seizure are not used for training, because they may not have epilepsy and would blur the interictal class; their recordings form a separate false alarm test set. |
| D-6 | Is LOPO feasible on a laptop if TUSZ adds many eligible test patients? (Added in version 0.2.) | If the label report (VT-07) finds more than 40 eligible test patients in total, patient-grouped 10-fold cross-validation replaces LOPO, with patients assigned to folds using seed 0. Every patient is still tested only by a model that never saw their data. Otherwise LOPO is used. Reports state which scheme was used. |

**Common montage (D-4).** Left temporal chain: Fp1-F7, F7-T7, T7-P7, P7-O1. Right temporal chain: Fp2-F8, F8-T8, T8-P8, P8-O2. Left parasagittal chain: Fp1-F3, F3-C3, C3-P3, P3-O1. Right parasagittal chain: Fp2-F4, F4-C4, C4-P4, P4-O2. Midline: Fz-Cz, Cz-Pz.

**Cyton placement for live tests (D-4).** Electrodes at F7, T7, P7, O1, F8, T8, P8 and O2 give six derivations from the temporal chains: F7-T7, T7-P7, P7-O1, F8-T8, T8-P8 and P8-O2. This covers both temporal lobes and avoids Fp1 and Fp2, which pick up strong eye-blink artifacts.

## 3. Definitions

Times are measured in seconds from the start of each continuous recording, using the dataset's expert annotations for seizure onset and offset.

| Term | Definition |
|---|---|
| Seizure event | An annotated seizure. Seizures whose onset is less than 30 min after the previous seizure's offset are merged into that earlier event and are not used as separate prediction targets. |
| Eligible seizure | A seizure event whose preictal period (below) is at least 90% recorded. Only eligible seizures produce preictal labels and count toward event sensitivity. The number of ineligible seizures is reported for every patient. |
| Preictal | From 30 min before onset to 5 s before onset (D-1). In the framework of Winterhalder et al. (2003), this is a seizure prediction horizon (SPH) of 5 s and a seizure occurrence period (SOP) of 29 min 55 s. |
| SPH gap | The last 5 s before onset. Excluded from training and from window-level metrics. |
| Ictal | From onset to offset of any annotated seizure, including merged and ineligible seizures. |
| Interictal | At least 4 h from every seizure onset and offset in the same recording timeline. TUSZ follows D-5. |
| Excluded | Any time not covered by the rows above (for example, 30 min to 4 h before onset, or up to 4 h after offset). Excluded time is not used for training or window-level metrics, but false alarms raised during it still count (see False alarm rate). |
| Window label | Each window is labeled by its end time, which is when a real-time system would output its score. |
| Eligible test patient | A patient with at least one eligible seizure and at least 1 h of interictal data. Other patients may still be used for training. |
| Alarm | A discrete warning raised by the alarm logic. After an alarm, no new alarm is raised for 30 min (the refractory period). |
| True alarm | An alarm followed by the onset of a seizure event between 5 s and 30 min later. |
| False alarm | Any alarm that is not a true alarm. |
| Predicted seizure | An eligible seizure preceded by at least one true alarm. |
| Event sensitivity | Predicted seizures divided by eligible seizures. |
| False alarm rate (FAR) | False alarms divided by recorded hours outside preictal and ictal periods, multiplied by 24. Reported as false alarms per 24 h. |
| Time in warning | Fraction of recorded time during which an alarm's 30 min warning period is active. Reported alongside sensitivity, because frequent alarms can inflate sensitivity. |
| Warning time | Time from a true alarm to the seizure onset it predicts. The share of true alarms arriving at least 30 s before onset is also reported, as a measure of whether users would have time to act. |
| Chance comparison | Sensitivity is compared with a random predictor raising alarms at the same FAR (Schelter et al., 2006). The chance probability of predicting one seizure is 1 − exp(−λ · SOP), where λ is the FAR per hour and SOP is 29 min 55 s. A one-sided binomial test gives the p-value. |

## 4. Test conditions

**Environment.** MacBook with Apple M4, macOS, Python 3.10 or later. Each results report records the output of `pip freeze` and the Git commit of the code under test.

**Data.** Siena Scalp EEG 1.0.0, CHB-MIT Scalp EEG 1.0.0, TUSZ 2.0.6, TUAR 3.0.1, and EEG During Mental Arithmetic Tasks 1.0.0, stored under `data/raw/`. Their checksums are recorded by VT-01, and any later test that finds different checksums is invalid. Recordings from TUSZ patients with no annotated seizure, and the mental arithmetic recordings, are used only for false alarm testing (D-5).

**Seeds.** Seeds 0, 1, 2, 3 and 4 are pre-registered here. Every model result is reported for all five seeds as mean and standard deviation. No seed is dropped or replaced after results are seen.

**Thresholds.** In every cross-patient fold (LOPO, or grouped folds under D-6), 20% of the training patients (chosen with the fold's seed) are held out as an inner validation set. The operating threshold is the lowest threshold whose FAR on the inner validation set is at or below the deliverable's FAR target (Section 6). The held-out test patient is never used to choose thresholds, normalization statistics, or any other parameter.

**Confidence intervals.** 95% intervals are computed by bootstrap over patients (1000 resamples, seed 0).

**Parameters.** All pipeline parameters are read from `configs/default.yaml`. Entries marked (VTP) there are fixed by this plan.

## 5. Requirements

| ID | Requirement |
|---|---|
| REQ-D1 | Every raw data file used is inventoried with its checksum, and dataset-level counts are generated from the data. |
| REQ-H1 | The loader reads Siena, CHB-MIT and TUSZ and outputs every recording in one format: modern 10-20 channel names, 256 Hz, microvolts, the 18-derivation bipolar montage (D-4), and seizure annotations in seconds from recording start. |
| REQ-H2 | Older channel names are mapped to modern names: T3 to T7, T4 to T8, T5 to P7, T6 to P8. Dataset-specific label formats (for example `EEG T3-REF`) are handled. |
| REQ-H3 | Seizure annotation times are unchanged by harmonization. |
| REQ-H4 | Non-EEG and unrecognized channels are removed and logged, never silently mapped. |
| REQ-L1 | Windows are labeled according to Section 3. |
| REQ-L2 | A per-patient label report gives eligible and ineligible seizures and hours of each label. |
| REQ-M1 | The classifier accepts any set of available channels and outputs per-window probabilities for preictal, ictal and interictal, plus a continuous preictal risk score. |
| REQ-E1 | Cross-patient evaluation uses leave-one-patient-out (LOPO), or patient-grouped folds under D-6, with no data from the test patient in training, validation or normalization. |
| REQ-E2 | Model results use the pre-registered seeds and are reproducible. |
| REQ-E3 | Thresholds are derived only from training patients, using the rule in Section 4. |
| REQ-E4 | Metrics follow the definitions in Section 3. |
| REQ-A1 | Alarm logic converts the risk score into discrete alarms, with no new alarm during the 30 min refractory period. |
| REQ-A2 | Alarm logic is causal: an alarm at time t depends only on scores up to time t. |
| REQ-U1 | The user interface replays a dataset recording showing EEG, risk score, threshold, alarms with times, and annotated seizure onsets. |
| REQ-R1 | Live Cyton data passes through the same harmonization, model and alarm code as offline data. |
| REQ-R2 | Live processing keeps up with real time. |
| REQ-R3 | A per-subject interictal baseline is computed from the first 10 min of each live session, before alarms are evaluated. |
| REQ-R4 | Each live session produces a report of duration, alarms fired and alarm times. |
| REQ-X1 | The README explains the data used, the code, the tests, and current metrics. |

## 6. Test cases

### Acceptance targets

| Metric | Deliverable 1 | Deliverable 2 | Deliverable 3 |
|---|---|---|---|
| Mean LOPO AUROC, preictal vs interictal | Above 0.50, with the 95% interval excluding 0.50. Nice to have: 0.65 or higher. | At least 15% relative improvement over D1 (D-2). Nice to have: 0.75 or higher. | Nice to have: 0.80 or higher. |
| Event sensitivity | Reported | At least 80% (D-3) | Not applicable (no seizures in live tests) |
| False alarms per 24 h | 10 or fewer (proposed) | 5 or fewer (D-3) | Live: fewer than 1 per 10 min |
| Chance comparison | Reported | p < 0.05 | Not applicable |

### 6.1 Deliverable 1

#### VT-01 Data inventory and integrity

| Field | Detail |
|---|---|
| Requirement | REQ-D1 |
| Type | Verification |
| Method | `scripts/audit_data.py` walks `data/raw/`, records every file with its size and SHA-256 checksum, opens every EDF header, and counts patients, recordings, recorded hours and annotated seizures per dataset. The script is run twice. |
| Pass | A manifest covers all five datasets. Every EDF header opens, or each failure is logged with a reason. The second run reproduces the same checksums and counts. |
| Evidence | `results/d1/data_manifest.csv`, `results/d1/data_audit.md` |

#### VT-02 Channel name mapping

| Field | Detail |
|---|---|
| Requirement | REQ-H2, REQ-H4 |
| Type | Verification |
| Method | Unit tests with synthetic channel lists covering old and new names, TUH-style labels (`EEG T3-REF`, `EEG T3-LE`), CHB-MIT bipolar labels, and non-EEG channels (ECG, EMG, photic). Then the mapping runs on every recording in the corpus. |
| Pass | All unit test cases map as expected. On the corpus, every channel is either mapped or listed in the exclusion log, and zero EEG channels are left unmapped. |
| Evidence | `tests/test_harmonize.py`, `results/d1/channel_log.csv` |

#### VT-03 Resampling and units

| Field | Detail |
|---|---|
| Requirement | REQ-H1 |
| Type | Verification |
| Method | Synthetic 10 Hz sine waves of known amplitude at 250, 400, 500 and 512 Hz are resampled to 256 Hz. On the real corpus, the median absolute amplitude of each harmonized channel is checked. |
| Pass | Dominant frequency within ±0.1 Hz, amplitude within ±1%, and output length equal to duration × 256 ± 1 sample. On the corpus, at least 95% of channels have a median absolute amplitude between 1 and 200 µV; channels outside that range are listed. |
| Evidence | `tests/test_harmonize.py`, `results/d1/amplitude_check.csv` |

#### VT-04 Montage conversion

| Field | Detail |
|---|---|
| Requirement | REQ-H1 |
| Type | Verification |
| Method | Synthetic referential signals with known values are converted to the D-4 montage. The same signals are also re-referenced to the average and to linked ears before conversion. |
| Pass | Every derivation equals the difference of its two electrodes to within 1e-6 µV, and the output is the same within 1e-6 µV whichever reference was used. Derivations with a missing electrode are marked absent, not filled. |
| Evidence | `tests/test_harmonize.py` |

#### VT-05 Annotation preservation

| Field | Detail |
|---|---|
| Requirement | REQ-H3 |
| Type | Verification |
| Method | For every seizure in Siena, CHB-MIT and TUSZ, harmonized onset and offset are compared with the source annotation. Ten seizures (at least three per dataset) are chosen at random with seed 0 and plotted with their onset markers for visual review. |
| Pass | 100% of onsets and offsets match within ±1 sample at 256 Hz. The visual review finds no misplaced markers. |
| Evidence | `results/d1/annotation_check.csv`, `results/d1/figures/` |

#### VT-06 Labeling rules

| Field | Detail |
|---|---|
| Requirement | REQ-L1 |
| Type | Verification |
| Method | Unit tests on synthetic recording timelines: a single seizure; two seizures less than 30 min apart (merged); a seizure with less than 90% of its preictal period recorded (ineligible); windows ending just inside and just outside each boundary; the SPH gap; the 4 h interictal rule; a seizure-free session; a TUSZ session containing a seizure but lacking file start times (no interictal windows); and a TUSZ patient with no seizures (false alarm set only). |
| Pass | Every case produces the expected labels. |
| Evidence | `tests/test_labels.py` |

#### VT-07 Label accounting

| Field | Detail |
|---|---|
| Requirement | REQ-L2 |
| Type | Verification |
| Method | The relabeled corpus is summarized per patient: eligible and ineligible seizures, and hours of preictal, ictal, interictal and excluded time. |
| Pass | The report exists for every patient, and for each recording the label durations add up to the recorded duration within one window. |
| Evidence | `results/d1/label_report.csv` |

#### VT-08 Patient separation

| Field | Detail |
|---|---|
| Requirement | REQ-E1 |
| Type | Verification |
| Method | Automated checks in every LOPO fold that the test patient's ID does not appear in the training or inner validation sets, and that normalization statistics are computed without the test patient's labels. Patient IDs are prefixed by dataset so IDs from different datasets cannot collide. |
| Pass | Zero overlaps across all folds and seeds. |
| Evidence | `tests/test_lopo.py`, per-fold logs in `results/d1/` |

#### VT-09 Seed protocol and reproducibility

| Field | Detail |
|---|---|
| Requirement | REQ-E2 |
| Type | Verification |
| Method | One fold is trained twice with seed 0. All results tables are checked for all five pre-registered seeds. |
| Pass | The two runs differ by no more than 0.005 in AUROC. Every results table reports all five seeds. |
| Evidence | `results/d1/reproducibility.json` |

#### VT-10 Threshold derivation

| Field | Detail |
|---|---|
| Requirement | REQ-E3 |
| Type | Verification |
| Method | Each fold logs its inner validation patients, the chosen threshold, and the time the threshold was fixed. The code is reviewed to confirm the test patient's scores are computed only after the threshold is fixed. |
| Pass | Every fold's threshold comes from inner validation patients only, using the Section 4 rule. |
| Evidence | Per-fold threshold logs in `results/d1/` |

#### VT-11 Cross-patient LOPO classification

| Field | Detail |
|---|---|
| Requirement | REQ-M1, REQ-E1, REQ-E4 |
| Type | Verification |
| Method | Cross-patient evaluation (LOPO, or grouped folds under D-6) over every eligible test patient in Siena, CHB-MIT and TUSZ, for all five seeds. Reported: per-patient AUROC (preictal vs interictal), three-class confusion matrix, macro F1, and mean and standard deviation across seeds. |
| Pass | The pipeline completes for 100% of eligible test patients, and mean AUROC is above 0.50 with a 95% interval that excludes 0.50. Nice to have: mean AUROC of 0.65 or higher. |
| Evidence | `results/d1/lopo_metrics.csv` |

#### VT-12 Montage-agnostic behavior

| Field | Detail |
|---|---|
| Requirement | REQ-M1 |
| Type | Characterization |
| Method | The trained models from VT-11 score each test patient with (a) all available channels, (b) a random 50% of channels (seed 0), and (c) only the six Cyton derivations listed in Section 2. |
| Pass | All three conditions run without error. The AUROC under each condition is reported; no threshold. |
| Evidence | `results/d1/channel_subset_metrics.csv` |

#### VT-13 Baseline alarm performance

| Field | Detail |
|---|---|
| Requirement | REQ-A1, REQ-E4 |
| Type | Verification |
| Method | Initial alarm logic is applied to the LOPO risk scores from VT-11, using thresholds from VT-10 with a FAR target of 10 per 24 h. FAR is also reported separately on the false alarm test sets (TUSZ patients without seizures, and mental arithmetic). |
| Pass | FAR of 10 or fewer per 24 h (proposed D1 acceptance). Event sensitivity, time in warning, warning times and the chance comparison are reported. |
| Evidence | `results/d1/alarm_metrics.csv` |

#### VT-14 Comparison with v1

| Field | Detail |
|---|---|
| Requirement | None (course plan item) |
| Type | Characterization |
| Method | A table compares v1 and v2 by dataset, evaluation split (within-patient or cross-patient), window definition, metrics and results, using v1's own reported numbers. No v1 code or model is run. |
| Pass | The table is complete and every difference in protocol is stated, so results are not compared as if they used the same protocol. |
| Evidence | `docs/verification_results/D1.md` |

### 6.2 Deliverable 2

#### VT-15 Improvement over Deliverable 1

| Field | Detail |
|---|---|
| Requirement | REQ-E1, REQ-E2 |
| Type | Verification |
| Method | The D2 model is evaluated on the same folds and seeds as the frozen D1 model. A paired Wilcoxon signed-rank test on per-patient AUROC is reported. |
| Pass | Mean LOPO AUROC improves by at least 15% relative to D1 (D-2). Nice to have: 0.75 or higher. |
| Evidence | `results/d2/comparison_d1_d2.csv` |

#### VT-16 Alarm logic unit tests

| Field | Detail |
|---|---|
| Requirement | REQ-A1, REQ-A2 |
| Type | Verification |
| Method | Synthetic risk-score traces: (a) a score that stays above threshold for 2 h; (b) a brief spike shorter than the persistence setting; (c) a score oscillating around the threshold; (d) a trace where scores after time t are changed. |
| Pass | (a) Alarms are at least 30 min apart. (b) No alarm. (c) No repeated alarms within the refractory period. (d) Alarms before time t are unchanged. |
| Evidence | `tests/test_alarm.py` |

#### VT-17 Event-level prediction performance

| Field | Detail |
|---|---|
| Requirement | REQ-A1, REQ-E4 |
| Type | Verification |
| Method | Final alarm logic on LOPO risk scores, with thresholds from the Section 4 rule and a FAR target of 5 per 24 h. FAR is also reported separately on the false alarm test sets. |
| Pass | Event sensitivity of at least 80%, FAR of 5 or fewer per 24 h, and chance comparison p < 0.05. Time in warning and warning times are reported. |
| Evidence | `results/d2/alarm_metrics.csv` |

#### VT-18 Cross-dataset generalization (nice to have)

| Field | Detail |
|---|---|
| Requirement | REQ-M1 |
| Type | Characterization |
| Method | A model trained only on Siena is tested on CHB-MIT and TUSZ. |
| Pass | AUROC, event sensitivity and FAR are reported for each test dataset. |
| Evidence | `results/d2/cross_dataset.csv` |

#### VT-19 Channel attribution (nice to have)

| Field | Detail |
|---|---|
| Requirement | REQ-M1 |
| Type | Characterization |
| Method | For each alarm, channel contributions are estimated by removing one channel at a time and measuring the change in risk score. As a check, the same method is run on a model with randomized weights. |
| Pass | Attributions are produced for every alarm in the test set, and they differ from the randomized-model attributions. |
| Evidence | `results/d2/attribution/` |

#### VT-20 README completeness

| Field | Detail |
|---|---|
| Requirement | REQ-X1 |
| Type | Verification |
| Method | The README is checked against the course plan: data use, code written so far, tests performed, verification metrics, and current model metrics. |
| Pass | Every item is present and the metrics in the README match the results files. |
| Evidence | `README.md` |

### 6.3 Deliverable 3

Live tests use the developer's own seizure-free EEG recorded with an OpenBCI Cyton. Because no seizures occur, every alarm in a live session is a false alarm; live tests measure false alarms and system behavior, not sensitivity. Electrode positions are documented with a photo before each session. Raw live recordings are stored under `data/` and never committed. Before publishing results from self-recorded EEG, confirm with the course instructor whether an IRB determination is needed.

#### VT-21 Replay consistency

| Field | Detail |
|---|---|
| Requirement | REQ-U1 |
| Type | Verification |
| Method | One recording each from Siena, CHB-MIT and TUSZ is replayed in the user interface. |
| Pass | The interface shows EEG, risk score, threshold, alarms with times, and annotated onsets, and its alarm times match the offline evaluation output exactly for all three recordings. |
| Evidence | Screenshots and logs in `results/d3/replay/` |

#### VT-22 Live acquisition integrity

| Field | Detail |
|---|---|
| Requirement | REQ-R1 |
| Type | Verification |
| Method | A 10 min Cyton session is streamed and saved to disk. The saved stream is then replayed offline through the same code. |
| Pass | Effective sample rate of 250 ± 1 Hz, packet loss of 1% or less, and identical alarms and risk scores in the live run and the offline replay. |
| Evidence | `results/d3/acquisition_check.json` |

#### VT-23 Real-time throughput

| Field | Detail |
|---|---|
| Requirement | REQ-R2 |
| Type | Verification |
| Method | Processing time per window is logged during a 60 min live session. |
| Pass | Processing time is at most 50% of the window step for at least 99% of windows, and the input buffer does not grow over the session. |
| Evidence | `results/d3/throughput.csv` |

#### VT-24 Live baseline

| Field | Detail |
|---|---|
| Requirement | REQ-R3 |
| Type | Verification |
| Method | The first 10 min of each live session are used to compute the per-subject baseline, which is saved before alarm evaluation starts. |
| Pass | A baseline file with a timestamp earlier than the first evaluated window exists for every session. |
| Evidence | `results/d3/baselines/` |

#### VT-25 Seizure-free live session

| Field | Detail |
|---|---|
| Requirement | REQ-R4 |
| Type | Verification |
| Method | At least 60 min of resting, seizure-free recording after the baseline period. |
| Pass | The session report gives duration, alarm count and alarm times, and there are fewer than 1 alarm per 10 min (course plan). The rate is also compared with the D2 target of 5 per 24 h. |
| Evidence | `results/d3/live_session_report.md` |

#### VT-26 Artifact robustness (nice to have)

| Field | Detail |
|---|---|
| Requirement | REQ-M1, REQ-A1 |
| Type | Characterization |
| Method | Live: scripted blocks of eye blinks, jaw clenching, chewing, talking, head movement and walking, each performed three times for 30 s with 2 min of rest between blocks. Offline: FAR on artifact-annotated segments from TUAR. |
| Pass | Alarms and channel attributions (if VT-19 is complete) are reported per artifact type. |
| Evidence | `results/d3/artifacts.csv` |

## 7. Traceability

| Requirement | Tests | Deliverable |
|---|---|---|
| REQ-D1 | VT-01 | 1 |
| REQ-H1 | VT-03, VT-04 | 1 |
| REQ-H2 | VT-02 | 1 |
| REQ-H3 | VT-05 | 1 |
| REQ-H4 | VT-02 | 1 |
| REQ-L1 | VT-06 | 1 |
| REQ-L2 | VT-07 | 1 |
| REQ-M1 | VT-11, VT-12, VT-18, VT-19, VT-26 | 1, 2, 3 |
| REQ-E1 | VT-08, VT-11, VT-15 | 1, 2 |
| REQ-E2 | VT-09, VT-15 | 1, 2 |
| REQ-E3 | VT-10 | 1 |
| REQ-E4 | VT-11, VT-13, VT-17 | 1, 2 |
| REQ-A1 | VT-13, VT-16, VT-17, VT-26 | 1, 2, 3 |
| REQ-A2 | VT-16 | 2 |
| REQ-U1 | VT-21 | 3 |
| REQ-R1 | VT-22 | 3 |
| REQ-R2 | VT-23 | 3 |
| REQ-R3 | VT-24 | 3 |
| REQ-R4 | VT-25 | 3 |
| REQ-X1 | VT-20 | 2 |

## 8. Recording results and deviations

Each deliverable has a report in `docs/verification_results/` (`D1.md`, `D2.md`, `D3.md`) with one row per test: test ID, result, pass or fail, evidence path, and the commit hash of this plan. Per-patient results for every test are kept, including failed tests. The Deliverable 3 report also compares its results with the Deliverable 1 and 2 reports.

A deviation is any change to a requirement, method or criterion after the plan is frozen. Each deviation creates a new plan version and an entry in Section 9 with the reason. Results report which plan version they were tested against.

## 9. Document history

| Version | Date | Change | Author |
|---|---|---|---|
| 0.1 | 2026-09-25 | Initial draft from the course plan | Kevin Kim |
| 0.2 | 2026-09-25 | Resolved D-1 to D-5 (preictal ends 5 s before onset; common montage; TUSZ interictal rule); added D-6 | Kevin Kim |

## 10. References

Winterhalder, M., Maiwald, T., Voss, H. U., Aschenbrenner-Scheibe, R., Timmer, J., & Schulze-Bonhage, A. (2003). The seizure prediction characteristic: A general framework to assess and compare seizure prediction methods. *Epilepsy & Behavior*, 4(3), 318–325.

Schelter, B., Winterhalder, M., Maiwald, T., Brandt, A., Schad, A., Schulze-Bonhage, A., & Timmer, J. (2006). Testing statistical significance of multivariate time series analysis techniques for epileptic seizure prediction. *Chaos*, 16(1), 013108.

International Medical Device Regulators Forum (2014). *Software as a Medical Device: Possible Framework for Risk Categorization and Corresponding Considerations* (IMDRF/SaMD WG/N12).

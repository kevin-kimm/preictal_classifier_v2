# Verification Test Plan: preictal_classifier_v2

## 1. Purpose

This plan lists every test for Deliverables 1–3, how each one is run, and what counts as a pass or fail. I'm writing it before any testing and freezing it in Git as v1.0, so the commit history shows the criteria came first.

Results go in `docs/verification_results/` (one file per deliverable), including failed tests and per-patient data. Each results file cites the commit hash of the plan version it was tested against. If something has to change after v1.0, it becomes a new version with the reason logged in Section 9. Criteria don't get edited to fit results.

There are two kinds of test. Verification tests have a pass/fail threshold. Characterization tests measure and report something I don't have a defensible threshold for yet.

## 2. Decisions

The 18 derivations:

| Chain | Derivations |
|---|---|
| Left temporal | Fp1-F7, F7-T7, T7-P7, P7-O1 |
| Right temporal | Fp2-F8, F8-T8, T8-P8, P8-O2 |
| Left parasagittal | Fp1-F3, F3-C3, C3-P3, P3-O1 |
| Right parasagittal | Fp2-F4, F4-C4, C4-P4, P4-O2 |
| Midline | Fz-Cz, Cz-Pz |

For live tests, the Cyton's 8 electrodes go at F7, T7, P7, O1, F8, T8, P8 and O2. That gives 6 derivations along both temporal chains (F7-T7, T7-P7, P7-O1, F8-T8, T8-P8, P8-O2) and skips Fp1/Fp2, which pick up a lot of blink artifact.

**D-5. Interictal data in TUSZ.** Many TUSZ sessions are short, and the time between sessions isn't known precisely. For TUSZ patients with at least one seizure, sessions with no seizure count as interictal. Sessions that contain a seizure give no interictal windows unless file start times show a window is at least 4 h from every seizure in that session. TUSZ patients with no annotated seizures aren't used for training, since some may not have epilepsy. Their recordings are used as a separate false-alarm test set.

**D-6. LOPO vs. grouped cross-validation.** Five seeds times one fold per patient could take days on a laptop if TUSZ adds a lot of patients. If the label report (VT-07) finds more than 40 eligible test patients, I'll use patient-grouped 10-fold cross-validation instead of LOPO, with fold assignment using seed 0. Every patient is still only tested by a model that never saw their data. Results say which scheme was used.

## 3. Definitions

Times are in seconds from the start of each continuous recording. Seizure onsets and offsets come from each dataset's expert annotations.

| Term | Definition |
|---|---|
| Seizure event | An annotated seizure. A seizure that starts less than 30 min after the previous one ends is merged into it. |
| Eligible seizure | A seizure event with at least 90% of its preictal window recorded. Only these get preictal labels and count toward sensitivity. The number of ineligible seizures is reported per patient. |
| Preictal | Onset − 30 min to onset − 5 s. In Winterhalder et al. (2003) terms: SPH = 5 s, SOP = 29 min 55 s. |
| SPH gap | The last 5 s before onset. Not used for training or window-level metrics. |
| Ictal | Onset to offset of any annotated seizure, including merged and ineligible ones. |
| Interictal | At least 4 h from every seizure onset and offset in the same recording timeline. TUSZ uses D-5. |
| Excluded | Everything else, e.g. 30 min to 4 h before onset, or up to 4 h after offset. Not used for training or window metrics, but false alarms during excluded time still count. |
| Window label | Set by the window's end time, since that's when a real-time system would output the score. |
| Eligible test patient | At least one eligible seizure and at least 1 h of interictal data. Other patients can still be used for training. |
| Alarm | A warning from the alarm logic, followed by a 30 min refractory period with no new alarms. |
| True / false alarm | True if a seizure onset follows within 5 s to 30 min. Otherwise false. |
| Sensitivity | Eligible seizures with at least one true alarm, divided by all eligible seizures. |
| False alarm rate (FAR) | False alarms per hour of recording outside preictal and ictal time, × 24. Reported per 24 h. |
| Time in warning | Fraction of recorded time inside an active 30 min warning. Reported with sensitivity, since frequent alarms can inflate sensitivity. |
| Warning time | Time from a true alarm to onset. I also report the share of true alarms that come at least 30 s before onset, as a check on whether a user would have time to act. |
| Chance level | A random predictor at the same FAR (Schelter et al., 2006). Chance of predicting one seizure = 1 − exp(−λ · SOP), with λ = FAR per hour. Compared using a one-sided binomial test. |

## 4. Test setup

**Hardware and software.** M4 MacBook, macOS, Python 3.13 in a virtual environment. Package versions are pinned in `requirements-lock.txt`. Each results report records `pip freeze` and the commit of the code being tested.

**Data.** Siena Scalp EEG 1.0.0, CHB-MIT Scalp EEG 1.0.0, TUSZ 2.0.6, TUAR 3.0.1 and EEG During Mental Arithmetic Tasks 1.0.0, all under `data/raw/`. VT-01 records their checksums. If the checksums change later, any test run after the change is invalid. TUSZ patients without seizures and the mental arithmetic recordings are only used for false-alarm testing (D-5).

**Seeds.** 0, 1, 2, 3 and 4, fixed here. Every model result is reported for all five seeds as mean ± SD. No seeds get dropped or swapped after seeing results.

**Thresholds.** In each cross-patient fold, 20% of the training patients are held out as an inner validation set, chosen with that fold's seed. The operating threshold is the lowest one that keeps inner-validation FAR at or below the target: 10 per 24 h for D1, 5 per 24 h for D2. The test patient is never used for thresholds, normalization, or any other tuning.

**Confidence intervals.** 95%, bootstrapped over patients (1000 resamples, seed 0).

**Parameters.** Pipeline settings live in `configs/default.yaml`. Settings marked (VTP) there are fixed by this plan.

## 5. Requirements

| ID | Requirement |
|---|---|
| REQ-D1 | Every raw data file is inventoried with a checksum, and dataset counts come from the data itself. |
| REQ-H1 | The loader reads Siena, CHB-MIT and TUSZ and outputs one format: modern 10-20 names, 256 Hz, µV, the D-4 bipolar montage, and seizure annotations in seconds from recording start. |
| REQ-H2 | Old channel names are mapped to new ones (T3→T7, T4→T8, T5→P7, T6→P8), including dataset-specific label formats like `EEG T3-REF`. |
| REQ-H3 | Harmonization doesn't change seizure annotation times. |
| REQ-H4 | Non-EEG and unrecognized channels are dropped and logged, not guessed. |
| REQ-L1 | Windows are labeled using the Section 3 rules. |
| REQ-L2 | There is a per-patient label report: eligible and ineligible seizures, and hours of each label. |
| REQ-M1 | The classifier takes whatever channels are available and outputs preictal / ictal / interictal probabilities per window, plus a continuous preictal risk score. |
| REQ-E1 | Evaluation is cross-patient (LOPO, or grouped folds under D-6), with no test-patient data in training, validation or normalization. |
| REQ-E2 | Model results use the fixed seeds and are reproducible. |
| REQ-E3 | Thresholds come only from training patients, using the Section 4 rule. |
| REQ-E4 | Metrics follow the Section 3 definitions. |
| REQ-A1 | The alarm logic turns the risk score into discrete alarms, with no new alarm during the 30 min refractory period. |
| REQ-A2 | The alarm logic is causal: an alarm at time t only depends on scores up to t. |
| REQ-U1 | The UI replays a dataset recording showing EEG, risk score, threshold, alarms with times, and annotated onsets. |
| REQ-R1 | Live Cyton data goes through the same harmonization, model and alarm code as offline data. |
| REQ-R2 | Live processing keeps up with real time. |
| REQ-R3 | A per-subject interictal baseline is computed from the first 10 min of each live session, before any alarms are evaluated. |
| REQ-R4 | Each live session produces a report with duration, number of alarms, and alarm times. |
| REQ-X1 | The README covers the data used, the code, the tests, and current metrics. |

## 6. Tests

### Acceptance targets

| Metric | D1 | D2 | D3 |
|---|---|---|---|
| Mean cross-patient AUROC (preictal vs interictal) | > 0.50, with the 95% CI above 0.50. Nice to have: ≥ 0.65 | ≥ 15% relative improvement over D1. Nice to have: ≥ 0.75 | Nice to have: ≥ 0.80 |
| Event sensitivity | Reported | ≥ 80% | n/a (no seizures in live data) |
| False alarms per 24 h | ≤ 10 | ≤ 5 | Live: < 1 per 10 min |
| Chance comparison | Reported | p < 0.05 | n/a |

### 6.1 Deliverable 1

#### VT-01 Data inventory
*REQ-D1 · verification*

Run `scripts/audit_data.py` on `data/raw/` twice. It records the size and SHA-256 of every file, opens every EDF header, and counts patients, recordings, hours and seizures per dataset.

**Pass:** the manifest covers all five datasets; every EDF header opens, or the failure is logged with a reason; the second run gives identical checksums and counts.

**Evidence:** `results/d1/data_manifest.csv`, `results/d1/data_audit.md`

#### VT-02 Channel name mapping
*REQ-H2, REQ-H4 · verification*

Unit tests with made-up channel lists: old and new names, TUH-style labels (`EEG T3-REF`, `EEG T3-LE`), CHB-MIT bipolar labels, and non-EEG channels (ECG, EMG, photic). Then run the mapping on every recording in the corpus.

**Pass:** all unit tests pass. On the corpus, every channel is either mapped or in the exclusion log, with zero unmapped EEG channels.

**Evidence:** `tests/test_harmonize.py`, `results/d1/channel_log.csv`

#### VT-03 Resampling and units
*REQ-H1 · verification*

Resample synthetic 10 Hz sine waves of known amplitude from 250, 400, 500 and 512 Hz to 256 Hz. On the real corpus, check the median absolute amplitude of each harmonized channel.

**Pass:** frequency within ±0.1 Hz, amplitude within ±1%, output length = duration × 256 ± 1 sample. On the corpus, at least 95% of channels have a median absolute amplitude between 1 and 200 µV; any outside that range are listed.

**Evidence:** `tests/test_harmonize.py`, `results/d1/amplitude_check.csv`

#### VT-04 Montage conversion
*REQ-H1 · verification*

Convert synthetic referential signals with known values to the D-4 montage. Repeat after re-referencing the same signals to the average and to linked ears.

**Pass:** each derivation equals the difference of its two electrodes to within 1e-6 µV, and the output is the same (within 1e-6 µV) regardless of reference. Derivations with a missing electrode are marked absent, not filled in.

**Evidence:** `tests/test_harmonize.py`

#### VT-05 Annotation preservation
*REQ-H3 · verification*

Compare harmonized onset and offset times with the source annotations for every seizure in Siena, CHB-MIT and TUSZ. Also plot 10 randomly chosen seizures (seed 0, at least 3 per dataset) with onset markers and check them by eye.

**Pass:** 100% of onsets and offsets match to within ±1 sample at 256 Hz, and none of the plotted markers are misplaced.

**Evidence:** `results/d1/annotation_check.csv`, `results/d1/figures/`

#### VT-06 Labeling rules
*REQ-L1 · verification*

Unit tests on synthetic timelines:
a single seizure;
two seizures less than 30 min apart (should merge);
a seizure with under 90% of its preictal window recorded (ineligible);
windows ending just inside and just outside each boundary;
the SPH gap;
the 4 h interictal rule;
a seizure-free session;
a TUSZ seizure session without file start times (no interictal windows);
a TUSZ patient with no seizures (false-alarm set only).

**Pass:** every case gives the expected labels.

**Evidence:** `tests/test_labels.py`

#### VT-07 Label report
*REQ-L2 · verification*

Summarize the relabeled corpus per patient: eligible and ineligible seizures, and hours of preictal, ictal, interictal and excluded time.

**Pass:** there's a row for every patient, and for each recording the label durations add up to the recording length within one window.

**Evidence:** `results/d1/label_report.csv`

#### VT-08 Patient separation
*REQ-E1 · verification*

Automated checks in every fold: the test patient's ID isn't in the training or inner validation sets, and normalization statistics don't use the test patient's labels. Patient IDs are prefixed with the dataset name so IDs from different datasets can't collide.

**Pass:** zero overlaps across all folds and seeds.

**Evidence:** `tests/test_lopo.py`, fold logs in `results/d1/`

#### VT-09 Seeds and reproducibility
*REQ-E2 · verification*

Train one fold twice with seed 0. Check that every results table includes all five seeds.

**Pass:** the two runs differ by at most 0.005 AUROC, and all five seeds appear in every results table.

**Evidence:** `results/d1/reproducibility.json`

#### VT-10 Threshold selection
*REQ-E3 · verification*

Each fold logs its inner validation patients, the chosen threshold, and when the threshold was fixed. Code review confirms the test patient is only scored after the threshold is fixed.

**Pass:** every fold's threshold comes only from its inner validation patients, using the Section 4 rule.

**Evidence:** threshold logs in `results/d1/`

#### VT-11 Cross-patient classification
*REQ-M1, REQ-E1, REQ-E4 · verification*

Cross-patient evaluation (LOPO, or grouped folds under D-6) over every eligible test patient in Siena, CHB-MIT and TUSZ, all five seeds. Report per-patient AUROC (preictal vs interictal), the 3-class confusion matrix, macro F1, and mean ± SD across seeds.

**Pass:** the pipeline finishes for every eligible test patient, and mean AUROC is above 0.50 with the 95% CI above 0.50. Nice to have: mean AUROC ≥ 0.65.

**Evidence:** `results/d1/lopo_metrics.csv`

#### VT-12 Channel subsets
*REQ-M1 · characterization*

Score each test patient with the VT-11 models using (a) all available channels, (b) a random 50% of channels (seed 0), and (c) only the 6 Cyton derivations from D-4.

**Pass:** all three run without errors. AUROC for each condition is reported, with no threshold.

**Evidence:** `results/d1/channel_subset_metrics.csv`

#### VT-13 Baseline alarms
*REQ-A1, REQ-E4 · verification*

Run the first version of the alarm logic on the VT-11 risk scores, with thresholds from VT-10 at a 10 per 24 h FAR target. Also report FAR separately on the false-alarm sets (TUSZ patients without seizures, and mental arithmetic).

**Pass:** FAR ≤ 10 per 24 h. Sensitivity, time in warning, warning times and the chance comparison are reported.

**Evidence:** `results/d1/alarm_metrics.csv`

#### VT-14 v1 vs v2 comparison
*Course plan item · characterization*

A table comparing v1 and v2: datasets, evaluation split (within-patient or cross-patient), window definitions, metrics, and results. v1 numbers come from v1's own reported results; no v1 code or models are run.

**Pass:** the table is complete, and every protocol difference is stated so the two aren't compared as if they were tested the same way.

**Evidence:** `docs/verification_results/D1.md`

### 6.2 Deliverable 2

#### VT-15 Improvement over D1
*REQ-E1, REQ-E2 · verification*

Evaluate the D2 model on the same folds and seeds as the frozen D1 model. Also report a paired Wilcoxon signed-rank test on per-patient AUROC.

**Pass:** mean AUROC improves by at least 15% relative to D1 (D-2). Nice to have: ≥ 0.75.

**Evidence:** `results/d2/comparison_d1_d2.csv`

#### VT-16 Alarm logic unit tests
*REQ-A1, REQ-A2 · verification*

Synthetic risk-score traces:
(a) above threshold for 2 h straight;
(b) a spike shorter than the persistence setting;
(c) a score bouncing around the threshold;
(d) the same trace with scores after time t changed.

**Pass:** (a) alarms at least 30 min apart; (b) no alarm; (c) no repeat alarms inside the refractory period; (d) alarms before t don't change.

**Evidence:** `tests/test_alarm.py`

#### VT-17 Event-level performance
*REQ-A1, REQ-E4 · verification*

Final alarm logic on the cross-patient risk scores, with thresholds from the Section 4 rule at a 5 per 24 h FAR target. FAR is also reported separately on the false-alarm sets.

**Pass:** sensitivity ≥ 80%, FAR ≤ 5 per 24 h, and chance comparison p < 0.05. Time in warning and warning times are reported.

**Evidence:** `results/d2/alarm_metrics.csv`

#### VT-18 Cross-dataset (nice to have)
*REQ-M1 · characterization*

Train on Siena only, then test on CHB-MIT and TUSZ.

**Pass:** AUROC, sensitivity and FAR reported for each test dataset.

**Evidence:** `results/d2/cross_dataset.csv`

#### VT-19 Channel attribution (nice to have)
*REQ-M1 · characterization*

For each alarm, remove one channel at a time and measure how much the risk score drops. As a sanity check, run the same thing on a model with randomized weights.

**Pass:** there's an attribution for every alarm in the test set, and it differs from the randomized-model attributions.

**Evidence:** `results/d2/attribution/`

#### VT-20 README check
*REQ-X1 · verification*

Check the README against the course plan: data use, code written, tests run, verification metrics, current model metrics.

**Pass:** everything is there, and the README numbers match the results files.

**Evidence:** `README.md`

### 6.3 Deliverable 3

Live tests use my own seizure-free EEG recorded on an OpenBCI Cyton. Since there are no seizures, every alarm in a live session is a false alarm. These tests measure false alarms and system behavior, not sensitivity. I'll photograph electrode placement before each session. Raw live recordings stay in `data/` and don't get committed. Before posting anything from my own recordings, I'll check with the instructor whether it needs an IRB determination.

#### VT-21 Replay consistency
*REQ-U1 · verification*

Replay one recording each from Siena, CHB-MIT and TUSZ in the UI.

**Pass:** the UI shows EEG, risk score, threshold, alarms with times, and annotated onsets, and its alarm times exactly match the offline results for all three recordings.

**Evidence:** screenshots and logs in `results/d3/replay/`

#### VT-22 Live acquisition
*REQ-R1 · verification*

Stream 10 min from the Cyton and save it to disk. Replay the saved file offline through the same code.

**Pass:** sample rate 250 ± 1 Hz, packet loss ≤ 1%, and identical risk scores and alarms between the live run and the offline replay.

**Evidence:** `results/d3/acquisition_check.json`

#### VT-23 Real-time throughput
*REQ-R2 · verification*

Log processing time per window during a 60 min live session.

**Pass:** processing takes at most 50% of the window step for at least 99% of windows, and the input buffer doesn't grow over the session.

**Evidence:** `results/d3/throughput.csv`

#### VT-24 Live baseline
*REQ-R3 · verification*

Compute the per-subject baseline from the first 10 min of each session and save it before alarm evaluation starts.

**Pass:** every session has a baseline file timestamped before its first evaluated window.

**Evidence:** `results/d3/baselines/`

#### VT-25 Seizure-free live session
*REQ-R4 · verification*

At least 60 min of resting, seizure-free recording after the baseline period.

**Pass:** the session report has duration, alarm count and alarm times, and there's less than 1 alarm per 10 min (course plan target). The rate is also compared with the D2 target of 5 per 24 h.

**Evidence:** `results/d3/live_session_report.md`

#### VT-26 Artifact robustness (nice to have)
*REQ-M1, REQ-A1 · characterization*

Live: blinking, jaw clenching, chewing, talking, head movement and walking, 3 × 30 s each with 2 min rest between. Offline: FAR on the artifact-labeled segments in TUAR.

**Pass:** alarms (and channel attributions, if VT-19 is done) reported for each artifact type.

**Evidence:** `results/d3/artifacts.csv`

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

## 8. Recording results

Each deliverable gets a results file (`D1.md`, `D2.md`, `D3.md`) in `docs/verification_results/` with one row per test: ID, result, pass/fail, evidence path, and the commit hash of this plan. Per-patient results are kept for every test, including failures. The D3 report also compares against the D1 and D2 results.

A deviation is any change to a requirement, method or pass criterion after v1.0. It gets a new plan version and an entry in Section 9 explaining why.

## 9. Revision history

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-09-25 | First draft from the course plan |
| 0.2 | 2026-09-25 | Settled D-1 to D-5 (preictal ends 5 s before onset, common montage, TUSZ interictal rule); added D-6; rewrote for clarity |

## 10. References

Winterhalder, M., Maiwald, T., Voss, H. U., Aschenbrenner-Scheibe, R., Timmer, J., & Schulze-Bonhage, A. (2003). The seizure prediction characteristic: A general framework to assess and compare seizure prediction methods. *Epilepsy & Behavior*, 4(3), 318–325.

Schelter, B., Winterhalder, M., Maiwald, T., Brandt, A., Schad, A., Schulze-Bonhage, A., & Timmer, J. (2006). Testing statistical significance of multivariate time series analysis techniques for epileptic seizure prediction. *Chaos*, 16(1), 013108.
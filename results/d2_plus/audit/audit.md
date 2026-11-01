# Annotation and artifact audit (development patients only)

Generated 2026-11-01T02:24:48 with `scripts/audit_annotations_artifacts.py` · risk scores from `frozen`, seed 0 · docs/evaluation_methods.md v1.32, Section 14.16. A characterization: nothing here changes a design, and no lockbox patient is loaded.

## chbmit_siena (25 patients, 805,568 windows, 5 min)

### 1. Seizure onsets

| Eligible seizures | Detected (within 2 min) | Median lead of detection (s; + = before onset) | Detection began 15 s to 5 min before onset | of which ≥ 60 s | Detector already on 5 min before |
|---|---|---|---|---|---|
| 111 | 54 (49%) | -14 | 1 (1%) | 1 | 0 |

A detection that begins seconds to a minute or two before the annotated onset suggests the onset was marked late. One that is already on 5 min before is more likely a change of state, an artifact or a genuine pre-seizure change, so those aren't counted as late onsets. Either way, only a look at the EEG (the figures in `review/`) can tell which.

In the flagged seizures, 0% of the pre-onset detection windows were also flagged as artifact (a run caused by movement looks the same to the detector).

**Does EEG just before the annotated onset drive the result?** 21 of 33,154 preictal test windows (0.1%) lie in or just before a flagged pre-onset detection. Without them, mean AUROC is 0.710 against 0.710 (-0.000; higher without them in 0 of 22; p = 0.32). Rule fixed in advance: a drop of 0.01 or more means seizure-like EEG just before the annotated onset contributes to the result, either because onsets are marked late (flattering) or because the change is a real early sign (the review decides). **Reading: no evidence that it does.**

### 2. Possible unannotated seizures in normal EEG

Sustained detections (≥ 30 s at or above the patient's detector threshold) inside normal EEG: **14** over 584 h (0.58 per 24 h); 13 of them are mostly artifact-flagged. The longest are in `review/` for a look by eye; a detection isn't a seizure until someone reading the EEG says so.

### 3. Artifacts

Windows flagged (a channel above 5 x or below 0.1 x its normal median; 99% of flags are 'above'):

| | Normal EEG | Preictal | Ictal |
|---|---|---|---|
| Flagged as artifact | 8.8% | 6.0% | 21.9% |

Seizures themselves are often flagged (high amplitude), which is expected. **Label confound check:** preictal windows are flagged 0.68 times as often as normal EEG (per patient +0.081, higher in 11 of 25, p = 0.33). Rule fixed in advance: 1.5 times or more with p < 0.05 means artifacts may be part of what the model learned as 'preictal'. **Reading: no evidence of a confound.**

**Risk and artifacts.** Dropping test windows with an artifact in the last 3 min (17.4% of them) changes mean AUROC from 0.710 to 0.715 (+0.009, higher in 10 of 20, p = 0.23). In normal EEG, 15.3% of windows follow a recent artifact, against 20.8% of each patient's top 5% by risk (lift 1.4x).

**Alarms** (frozen settings, ≤ 5 per 24 h target, 22 patients with alarm calibration): 19% of 63 false alarms and 21% of 14 true alarms had an artifact in the 3 min before, against 15% of normal EEG overall (false-alarm lift 1.2x). Rule fixed in advance: a lift of 1.5x or more makes an artifact gate worth pre-registering for v3. **Reading: not supported here.**

## seizeit2 (24 patients, 1,743,870 windows, 8 min)

### 1. Seizure onsets

| Eligible seizures | Detected (within 2 min) | Median lead of detection (s; + = before onset) | Detection began 15 s to 5 min before onset | of which ≥ 60 s | Detector already on 5 min before |
|---|---|---|---|---|---|
| 151 | 11 (7%) | -48 | 0 (0%) | 0 | 0 |

A detection that begins seconds to a minute or two before the annotated onset suggests the onset was marked late. One that is already on 5 min before is more likely a change of state, an artifact or a genuine pre-seizure change, so those aren't counted as late onsets. Either way, only a look at the EEG (the figures in `review/`) can tell which.

**Does EEG just before the annotated onset drive the result?** 0 of 48,056 preictal test windows (0.0%) lie in or just before a flagged pre-onset detection. Without them, mean AUROC is 0.669 against 0.669 (+0.000; higher without them in 0 of 14; p = 1). Rule fixed in advance: a drop of 0.01 or more means seizure-like EEG just before the annotated onset contributes to the result, either because onsets are marked late (flattering) or because the change is a real early sign (the review decides). **Reading: no evidence that it does.**

### 2. Possible unannotated seizures in normal EEG

Sustained detections (≥ 30 s at or above the patient's detector threshold) inside normal EEG: **18** over 1720 h (0.25 per 24 h); 11 of them are mostly artifact-flagged. The longest are in `review/` for a look by eye; a detection isn't a seizure until someone reading the EEG says so.

### 3. Artifacts

Windows flagged (a channel above 5 x or below 0.1 x its normal median; 96% of flags are 'above'):

| | Normal EEG | Preictal | Ictal |
|---|---|---|---|
| Flagged as artifact | 12.4% | 17.4% | 49.2% |
| Any channel above 150 µV RMS | 8.4% | 12.4% | 43.6% |

Seizures themselves are often flagged (high amplitude), which is expected. **Label confound check:** preictal windows are flagged 1.40 times as often as normal EEG (per patient +0.024, higher in 10 of 24, p = 0.77). Rule fixed in advance: 1.5 times or more with p < 0.05 means artifacts may be part of what the model learned as 'preictal'. **Reading: no evidence of a confound.**

**Risk and artifacts.** Dropping test windows with an artifact in the last 3 min (28.3% of them) changes mean AUROC from 0.669 to 0.668 (-0.002, higher in 6 of 14, p = 0.33). In normal EEG, 28.2% of windows follow a recent artifact, against 35.1% of each patient's top 5% by risk (lift 1.2x).

**Alarms** (frozen settings, ≤ 5 per 24 h target, 14 patients with alarm calibration): 42% of 158 false alarms and 31% of 61 true alarms had an artifact in the 3 min before, against 28% of normal EEG overall (false-alarm lift 1.5x). Rule fixed in advance: a lift of 1.5x or more makes an artifact gate worth pre-registering for v3. **Reading: worth testing.**


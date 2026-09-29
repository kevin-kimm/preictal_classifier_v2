# SeizeIT2 blind feasibility audit

Generated 2026-09-29T09:45:28 with `scripts/audit_seizeit2.py`. Only file listings, EDF headers and annotation column names and categories were read. No EEG samples were read, no seizure timings were looked at, and seizure numbers are totals across the whole dataset (docs/evaluation_methods.md v1.7, Section 12).

## Files

- Subjects: 125; subject-sessions: 125; files: 24877
- By type: .json 11012, .edf 11009, .tsv 2851, (none) 5
- EDF files readable: 11009 of 11009

## Recordings by modality

| Modality | EDF files | Hours | Channel labels (files) | Sampling rates, Hz (channels) | Units |
|---|---|---|---|---|---|
| ecg | 2804 | 11271 | ECG SD (2804); EDF Annotations (2804) | 256.0 (2804); 57.0 (2804) | uV (2804);  (2804) |
| eeg | 2850 | 11626 | EDF Annotations (2850); CROSStop SD (2340); BTEleft SD (1944); BTEright SD (1416) | 256.0 (5700); 57.0 (2850) | uV (5700);  (2850) |
| emg | 2804 | 11271 | EMG SD (2804); EDF Annotations (2804) | 256.0 (2804); 57.0 (2804) | uV (2804);  (2804) |
| mov | 2551 | 11173 | EDF Annotations (2551); ECGEMG SD ACC X (2499); ECGEMG SD ACC Y (2499); ECGEMG SD ACC Z (2499); ECGEMG SD GYR A (2490); ECGEMG SD GYR B (2490); ECGEMG SD GYR C (2490); EEG SD ACC X (2464); EEG SD ACC Y (2464); EEG SD ACC Z (2464); EEG SD GYR A (2340); EEG SD GYR B (2340) | 25.0 (29379); 57.0 (2551) | g (29373);  (2551); 10E-3 g (6) |

## EEG timing

- EEG files starting at exactly 00:00:00: 2850; other start times: 0 (many 00:00:00 starts would suggest anonymized clock times, as in TUSZ)
- EEG hours per subject: median 95, range 1–397

## Annotations (totals only)

- Event files: 2850
- Column sets: onset, duration, eventType, lateralization, localization, vigilance, confidence, channels, dateTime, recordingDuration (2850 files)
- Event categories: bckg (2313); impd (464); sz_foc_ia_nm (160); sz_foc_a_m_hyperkinetic (158); sz_foc_ia_m_hyperkinetic (100); sz_foc_a_nm (66); sz_foc_ia_m_automatisms (62); sz_foc_f2b (55); sz_foc_a_um (50); sz_foc_ua_um (41); sz_foc_ua_nm (40); sz_foc_a_nm_behavior (38); sz_foc_ia (35); sz_foc_ia_m_tonic (24); sz_foc_ua_nm_behavior (17)
- Seizure events in total: 883; subjects with at least one: 125; with at least two (needed for the patient-specific design): 97

## Recording timing (v1.8; recording start times only)

- scans.tsv files: 0; column sets: 
- EEG recordings with an acq_time: 0; of those at exactly midnight: 0

## Recording timing from the annotation files (v1.9; recording start times only)

- Annotation files with one dateTime for every row (a recording start): 2850; with differing dateTimes (event-level, not used): 0
- Of the recording starts, at exactly midnight: 2850
- recordingDuration matches the EDF duration within 2 s: 2850 of 2850
- Gaps between consecutive recordings in a session (next start minus previous end): 2725 gaps, median -3567 s, within ±60 s: 0 (0%), overlaps over 60 s: 2725, gaps over 1 h: 0

# Harmonization checks (VT-02 to VT-05)

Generated 2026-09-25T17:42:48 · commit 8f84b18 · Python 3.13.2 · 9249 recordings

## Results

| Test | Part | Result |
|---|---|---|
| VT-02 to VT-04 | Unit tests (`tests/test_harmonize.py`, `tests/test_loaders.py`) | PASS: 82 passed in 0.48s |
| VT-02 | Every channel mapped or logged; zero unmapped EEG channels | PASS: 0 unmapped EEG labels |
| VT-03 | ≥ 95% of derivations with median amplitude in 1–200 µV; lengths = duration × 256 ± 1 | PASS: 162681/165232 (98.5%) in range, 0 length mismatches |
| VT-04 | Montage conversion | See unit tests |
| VT-05 | Every seizure inside its recording, within ±1 sample; counts match VT-01 | PASS: 2908 seizures checked, 0 problems, 0 count mismatches |
| VT-05 | Visual review of 10 plotted seizures | PENDING: review the figures below |

## VT-02 channel mapping

Channel labels by how they were handled (distinct labels per dataset):

- excluded: duplicate of an earlier channel: 1
- excluded: empty placeholder channel: 2
- excluded: non-EEG signal: 65
- excluded: numbered channel with no electrode position: 244
- recognized, not needed for the montage: 72
- unrecognized label: 5
- used: 172

Recordings by number of derivations present (out of 18):

| Dataset | Derivations present: recordings |
|---|---|
| chbmit | 18: 686 |
| mental_arith | 18: 72 |
| siena | 18: 41 |
| tuar | 18: 310 |
| tusz | 18: 7515, 16: 625 |

Unrecognized labels without an EEG prefix (logged, not used):

mental_arith: `EDF Annotations`, siena: `A`, siena: `B`, siena: `C`, siena: `D`

## VT-03 amplitude

Median absolute amplitude per derivation (µV):

| Dataset | Derivations | In 1–200 µV | 5th pct | Median | 95th pct |
|---|---|---|---|---|---|
| chbmit | 12348 | 99.8% | 7.2 | 18.6 | 47.2 |
| mental_arith | 1296 | 100.0% | 2.7 | 4.9 | 8.8 |
| siena | 738 | 99.2% | 5.6 | 10.3 | 35.5 |
| tuar | 5580 | 99.7% | 3.7 | 9.1 | 34.3 |
| tusz | 145270 | 98.3% | 3.7 | 9.0 | 43.7 |

Out-of-range derivations are listed in `amplitude_check.csv`.

## VT-05 annotations

Seizures checked per dataset: chbmit 198, siena 47, tusz 2663. Excluded by corrections: tusz 1.
Seizure durations range from 2.0 s to 1720.8 s.

Seizures for visual review (red = annotated onset, blue = offset). Check that each onset marker lines up with a visible change in the EEG:

| Figure | Recording | Seizure |
|---|---|---|
| [seizure_01_chbmit.png](figures/seizure_01_chbmit.png) | chbmit_v1.0.0/chb13/chb13_19.edf | 1 |
| [seizure_02_chbmit.png](figures/seizure_02_chbmit.png) | chbmit_v1.0.0/chb24/chb24_14.edf | 1 |
| [seizure_03_chbmit.png](figures/seizure_03_chbmit.png) | chbmit_v1.0.0/chb13/chb13_62.edf | 1 |
| [seizure_04_siena.png](figures/seizure_04_siena.png) | siena_v1.0.0/PN00/PN00-3.edf | 1 |
| [seizure_05_siena.png](figures/seizure_05_siena.png) | siena_v1.0.0/PN06/PN06-5.edf | 1 |
| [seizure_06_siena.png](figures/seizure_06_siena.png) | siena_v1.0.0/PN12/PN12-1.2.edf | 1 |
| [seizure_07_tusz.png](figures/seizure_07_tusz.png) | tusz_v2.0.6/edf/train/aaaaapks/s002_2013/01_tcp_ar/aaaaapks_s002_t010.edf | 1 |
| [seizure_08_tusz.png](figures/seizure_08_tusz.png) | tusz_v2.0.6/edf/train/aaaaaksg/s001_2010/02_tcp_le/aaaaaksg_s001_t001.edf | 5 |
| [seizure_09_tusz.png](figures/seizure_09_tusz.png) | tusz_v2.0.6/edf/train/aaaaaibs/s002_2009/02_tcp_le/aaaaaibs_s002_t003.edf | 1 |
| [seizure_10_tusz.png](figures/seizure_10_tusz.png) | tusz_v2.0.6/edf/train/aaaaalnt/s001_2011/01_tcp_ar/aaaaalnt_s001_t000.edf | 4 |

## Flagged seizures for review

Seizures whose annotation was corrected (configs/annotation_corrections.yaml) or whose Siena list disagrees with the EDF start time. Compare the two figures for each: the onset should line up with a visible change in the EEG in the 'used' figure.

| Recording | Reason | Timing used | Alternative |
|---|---|---|---|
| siena_v1.0.0/PN00/PN00-3.edf | corrected: The seizure list gives the end time as 19.29.29, which is after the list's own registration end (18.57.13) and 61 min after onset (18.28.29). Assumed to be an hour typo for 18.29.29, the smallest edit that fits; that makes the seizure 60 s long, in line with PN00's other seizures. 18:29:29 is 825 s after the recording start (18:15:44). To be confirmed by eye in results/d1/figures/flagged_*. | [flagged_01_siena_PN00-3_used.png](figures/flagged_01_siena_PN00-3_used.png) | not plotted (original annotation is outside the recording) |
| siena_v1.0.0/PN05/PN05-3.edf | Seizures-list-PN05.txt entry 2: list gives registration start 06:01:23 but the EDF header says 06:01:13; the EDF header time is used | [flagged_02_siena_PN05-3_used.png](figures/flagged_02_siena_PN05-3_used.png) | [flagged_02_siena_PN05-3_alternative.png](figures/flagged_02_siena_PN05-3_alternative.png) |
| siena_v1.0.0/PN10/PN10-7.8.9.edf | Seizures-list-PN10.txt entry 7: list gives registration start 06:49:25 but the EDF header says 16:49:25; the EDF header time is used | [flagged_03_siena_PN10-7.8.9_used.png](figures/flagged_03_siena_PN10-7.8.9_used.png) | not plotted (timing implied by the list's registration start is outside the recording) |
| siena_v1.0.0/PN14/PN14-3.edf | Seizures-list-PN14.txt entry 3: list gives registration start 16:17:45 but the EDF header says 19:17:45; the EDF header time is used | [flagged_04_siena_PN14-3_used.png](figures/flagged_04_siena_PN14-3_used.png) | [flagged_04_siena_PN14-3_alternative.png](figures/flagged_04_siena_PN14-3_alternative.png) |

## Loader notes

- siena: Seizures-list-PN01.txt entry 1: 'PN01.edf' matched to PN01-1.edf (only EDF for this patient)
- siena: Seizures-list-PN01.txt entry 2: 'PN01.edf' matched to PN01-1.edf (only EDF for this patient)
- siena: Seizures-list-PN05.txt entry 2: list gives registration start 06:01:23 but the EDF header says 06:01:13; the EDF header time is used
- siena: Seizures-list-PN06.txt entry 1: 'PNO6-1.edf' matched to PN06-1.edf (letter O typed for zero)
- siena: Seizures-list-PN06.txt entry 2: 'PNO6-2.edf' matched to PN06-2.edf (letter O typed for zero)
- siena: Seizures-list-PN06.txt entry 4: 'PNO6-4.edf' matched to PN06-4.edf (letter O typed for zero)
- siena: Seizures-list-PN10.txt entry 3: used electrographic onset (15.43.53 (CLINICAL ONSET); 15.43.59 (ELECTRIC ONSET))
- siena: Seizures-list-PN10.txt entry 7: list gives registration start 06:49:25 but the EDF header says 16:49:25; the EDF header time is used
- siena: Seizures-list-PN11.txt entry 1: 'PN11-.edf' matched to PN11-1.edf (only EDF for this patient)
- siena: Seizures-list-PN14.txt entry 3: list gives registration start 16:17:45 but the EDF header says 19:17:45; the EDF header time is used
- correction applied: siena PN00-3.edf seizure 1 set_offset_s 825 (The seizure list gives the end time as 19.29.29, which is after the list's own registration end (18.57.13) and 61 min after onset (18.28.29). Assumed to be an hour typo for 18.29.29, the smallest edit that fits; that makes the seizure 60 s long, in line with PN00's other seizures. 18:29:29 is 825 s after the recording start (18:15:44). To be confirmed by eye in results/d1/figures/flagged_*.)
- correction applied: tusz aaaaapks_s016_t000.edf seizure 1 excluded (The .csv_bi file has a seizure row from 0.0000 to 0.0000 s (zero length), followed by seven normal seizure rows. A zero-length event can't be labeled. Excluding it doesn't change any labels, because the start of this file is within 4 h of the other seizures and so isn't interictal anyway.)

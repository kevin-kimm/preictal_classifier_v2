# Data audit (VT-01)

Generated 2026-09-25T15:43:24 · commit b34087e (uncommitted changes) · Python 3.13.2 · full run

## VT-01 checklist

| Criterion | Result |
|---|---|
| Manifest covers all five datasets | PASS |
| Every EDF header opens, or the failure is logged with a reason | PASS (0 failures logged) |
| Second run gives identical checksums and counts | PASS: Identical to the previous run (2026-09-25T15:42:34): same checksums and counts. |

## Summary

| Dataset | Files | Size (GB) | EDF | Headers failed | Patients | Hours | Seizures | Patients with seizures | Sampling rates (Hz: recordings) |
|---|---|---|---|---|---|---|---|---|---|
| chbmit | 857 | 45.8 | 686 | 0 | 24 | 982.94 | 198 | 24 | 256: 686 |
| mental_arith | 76 | 0.2 | 72 | 0 | 36 | 2.41 | 0 | 0 | 500: 72 |
| siena | 59 | 21.8 | 41 | 0 | 14 | 141.02 | 47 | 14 | 512: 41 |
| tuar | 669 | 5.8 | 310 | 0 | 213 | 99.98 | 161 | 28 | 250: 201, 256: 93, 400: 9, 512: 6, ... |
| tusz | 24427 | 84.7 | 8140 | 0 | 675 | 1474.79 | 2664 | 238 | 256: 6071, 250: 1171, 400: 658, 512: 130, ... |

Hidden files skipped (for example .DS_Store): 4

## Notes

**chbmit**

- RECORDS-WITH-SEIZURES lists 141 files; summary files give 141 files with seizures (2 differ)
- chb01 and chb21 are the same subject (per the CHB-MIT documentation); group them as one patient for cross-patient splits
- EDF files with header warnings: 1 (see the warning column in data_manifest.csv)

**siena**

- Seizure list names 'PN01.edf'; matched to PN01-1.edf (only EDF for this patient)
- Seizure list names 'PN11-.edf'; matched to PN11-1.edf (only EDF for this patient)
- Seizure list names 'PNO6-1.edf'; matched to PN06-1.edf (letter O typed for zero)
- Seizure list names 'PNO6-2.edf'; matched to PN06-2.edf (letter O typed for zero)
- Seizure list names 'PNO6-4.edf'; matched to PN06-4.edf (letter O typed for zero)

**tuar**

- EDF files without an artifact .csv: 0
- Recordings with seizure annotations (_seiz.csv): 42
- Artifact events by label: chew 764, chew_elec 43, chew_musc 24, elec 7698, elpp 8, eyem 11513, eyem_chew 312, eyem_elec 564, eyem_musc 4842, eyem_shiv 3, musc 10869, musc_elec 1368, shiv 42, shiv_elec 1
- Patients also in TUSZ: 69 of 213 (listed in tuar_tusz_overlap.csv)

**tusz**

- EDF files without a .csv_bi annotation file: 0
- Patients in more than one official split: 0
- Patients with no annotated seizures (false-alarm set under D-5): 437

## Dataset fingerprints

SHA-256 of each dataset's sorted list of (path, size, checksum). Identical fingerprints mean identical files.

| Dataset | Fingerprint |
|---|---|
| chbmit | `4917af0cafdfe9dc4461c990130ff8c1ab10392d2dd2a1f5fbb4ef867b7b725e` |
| mental_arith | `067d44c754bc2fccb9ce70f7de61f9a0ff50059ebf2ae46f9019ab2cb6eb872a` |
| siena | `e8ef771f939d74ddd6f0113592881e9434824d7db40965e008917bf3174478bc` |
| tuar | `ac977a584e8acf52161e1856b775e36fe6ee6899465b3d1274e1f1bddaa33b3d` |
| tusz | `638064a1d0ec6f05a5f411ec1dba6c91b49e3464899e46e42ea94f9b2232b96a` |

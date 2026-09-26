# Labels (VT-06, VT-07)

Generated 2026-09-26T10:10:35 · commit 1dfefa7 · Python 3.13.2 · windows 30 s, step 5 s

## Results

| Test | Result |
|---|---|
| VT-06 labeling rules (unit tests, `tests/test_labels.py`) | PASS: 33 passed in 0.43s |
| VT-07 a row for every patient | PASS: 748 of 748 patients |
| VT-07 label durations add up to each recording's length | PASS: 0 mismatches (label intervals, exact) |
| VT-07 windows cover each recording to within one window | PASS: 0 mismatches; 547 recordings shorter than one window |

## Per dataset

| Dataset | Patients | Recordings | Seizures | Events (after merging) | Eligible events | Eligible test patients | Preictal h | Ictal h | Interictal h | Excluded h |
|---|---|---|---|---|---|---|---|---|---|---|
| chbmit | 23 | 686 | 198 | 144 | 122 | 21 | 60.6 | 3.2 | 564.1 | 355.0 |
| mental_arith | 36 (36 false-alarm only) | 72 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 2.4 | 0.0 |
| siena | 14 | 41 | 47 | 47 | 40 | 4 | 19.9 | 0.8 | 22.4 | 97.9 |
| tusz | 675 (437 false-alarm only) | 8140 | 2663 | 1097 | 0 | 0 | 0.0 | 47.3 | 1052.8 | 374.8 |

Windows (30 s, step 5 s):

| Dataset | Preictal | Ictal | Interictal | Excluded |
|---|---|---|---|---|
| chbmit | 43,452 | 2,363 | 404,365 | 254,073 |
| mental_arith | 0 | 0 | 1,347 | 0 |
| siena | 14,367 | 582 | 16,093 | 70,273 |
| tusz | 0 | 32,899 | 730,109 | 258,473 |

## Cross-validation scheme (D-6)

Eligible test patients (at least one eligible seizure and at least 1 h interictal): **25**. The D-6 threshold is 40, so the scheme is **leave-one-patient-out**.

## Why seizures were not eligible

An event is eligible if at least 90% of its 30 min preictal period is recorded.

| Dataset | None of the preictal period recorded | Under 50% | 50-90% |
|---|---|---|---|
| chbmit | 0 | 12 | 10 |
| siena | 0 | 2 | 5 |
| tusz | 187 | 887 | 23 |

## Timelines

Recordings are placed in time using their EDF start times. A recording is labeled on its own when its position can't be trusted; none of its time is then interictal if its patient (or TUSZ session) has seizures.

Recordings labeled on their own: chbmit 2, tusz 7528.
Groups (patients or TUSZ sessions) whose recordings all report the same start time: tusz 1031.
Recordings that would start more than 60 s before the previous one ends: 2.
Timelines spanning more than one day: chbmit 22, siena 9.

- chbmit_v1.0.0/chb10/chb10_89.edf: would start 670 s before the previous recording ends; position unknown, labeled on its own
- chbmit_v1.0.0/chb18/chb18_36.edf: would start 3369 s before the previous recording ends; position unknown, labeled on its own

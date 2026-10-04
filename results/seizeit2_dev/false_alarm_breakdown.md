# False-alarm breakdown (v3 development diagnostic)

Forward-in-time simulation, SeizeIT2 development patients, steps after at least one learned seizure (docs/evaluation_methods.md v1.21). Rates are false alarms per 24 h of monitored normal EEG.

## 1. By learning stage and time since retraining

| Model | Thresholds | Target | 1 learned | 2 learned | 3 learned | 4 learned | 5+ learned | 0–6 h after retraining | 6–24 h after retraining | > 24 h after retraining |
|---|---|---|---|---|---|---|---|---|---|---|
| learning device | fixed | ≤ 5 | 13.0 | 4.7 | 3.8 | – | 17.3 | 9.6 | 13.6 | 18.9 |
| learning device | fixed | ≤ 1 | 6.3 | 0.9 | 1.9 | – | 14.0 | 6.4 | 9.1 | 12.6 |
| learning device | adaptive | ≤ 5 | 9.8 | 5.7 | 3.8 | – | 12.1 | 9.6 | 12.3 | 3.4 |
| learning device | adaptive | ≤ 1 | 5.4 | 0.9 | 1.9 | – | 8.0 | 6.4 | 7.4 | 0.0 |
| never learns | fixed | ≤ 5 | 11.2 | 6.6 | 3.8 | – | 3.8 | 9.0 | 6.3 | 4.4 |
| never learns | fixed | ≤ 1 | 6.0 | 3.8 | 1.9 | – | 2.5 | 4.9 | 3.6 | 2.9 |
| never learns | adaptive | ≤ 5 | 9.4 | 6.6 | 3.8 | – | 5.1 | 9.0 | 6.3 | 3.9 |
| never learns | adaptive | ≤ 1 | 5.4 | 4.7 | 1.9 | – | 2.5 | 4.9 | 4.2 | 0.0 |

## 2. Which patients

| Model | Thresholds | Target | False alarms | Share from the top 3 patients | Patients with any | Highest per-patient rate (per 24 h) |
|---|---|---|---|---|---|---|
| learning device | fixed | ≤ 5 | 156 | 60% | 13 | 37.7 (seizeit2:sub-065) |
| learning device | fixed | ≤ 1 | 104 | 75% | 13 | 27.9 (seizeit2:sub-074) |
| learning device | adaptive | ≤ 5 | 116 | 48% | 13 | 37.7 (seizeit2:sub-065) |
| learning device | adaptive | ≤ 1 | 68 | 51% | 13 | 17.2 (seizeit2:sub-034) |
| never learns | fixed | ≤ 5 | 79 | 48% | 13 | 26.7 (seizeit2:sub-112) |
| never learns | fixed | ≤ 1 | 45 | 60% | 13 | 19.6 (seizeit2:sub-086) |
| never learns | adaptive | ≤ 5 | 78 | 41% | 13 | 26.7 (seizeit2:sub-112) |
| never learns | adaptive | ≤ 1 | 43 | 51% | 13 | 15.7 (seizeit2:sub-086) |

Check: the logged false alarms match the simulation's own counts in every configuration.

Per patient, learning device with adaptive thresholds (≤ 5):

| Patient | False alarms | Monitored normal EEG (h) | Per 24 h |
|---|---|---|---|
| seizeit2:sub-065 | 4 | 2.5 | 37.7 |
| seizeit2:sub-073 | 16 | 21.1 | 18.2 |
| seizeit2:sub-034 | 8 | 11.1 | 17.2 |
| seizeit2:sub-113 | 18 | 27.9 | 15.5 |
| seizeit2:sub-074 | 22 | 38.7 | 13.6 |
| seizeit2:sub-086 | 8 | 18.3 | 10.5 |
| seizeit2:sub-001 | 7 | 22.8 | 7.4 |
| seizeit2:sub-002 | 12 | 39.2 | 7.4 |
| seizeit2:sub-029 | 3 | 10.1 | 7.1 |
| seizeit2:sub-100 | 13 | 45.9 | 6.8 |
| seizeit2:sub-103 | 5 | 25.7 | 4.7 |
| seizeit2:sub-005 | 0 | 0.4 | 0.0 |
| seizeit2:sub-050 | 0 | 0.0 | nan |
| seizeit2:sub-053 | 0 | 0.0 | nan |
| seizeit2:sub-067 | 0 | 0.0 | nan |
| seizeit2:sub-090 | 0 | 0.0 | nan |
| seizeit2:sub-112 | 0 | 8.1 | 0.0 |

## 3. Movement and muscle activity in the 5 min before each false alarm

"High" means above that patient's 90th percentile in sampled normal EEG, so about 10% of false alarms would be high by chance. Measures that couldn't be read (a missing file) are left out.

| Model | Thresholds | Target | High eeg muscle (n) | High movement (n) | High emg (n) |
|---|---|---|---|---|---|
| learning device | fixed | ≤ 5 | 11% (n=156, p=0.39) | 20% (n=155, p=0.00014) | 14% (n=153, p=0.085) |
| learning device | fixed | ≤ 1 | 15% (n=104, p=0.054) | 25% (n=103, p=7.3e-06) | 16% (n=103, p=0.05) |
| learning device | adaptive | ≤ 5 | 11% (n=116, p=0.38) | 15% (n=116, p=0.07) | 17% (n=114, p=0.018) |
| learning device | adaptive | ≤ 1 | 13% (n=68, p=0.24) | 21% (n=68, p=0.0067) | 18% (n=68, p=0.036) |
| never learns | fixed | ≤ 5 | 9% (n=79, p=0.69) | 12% (n=75, p=0.33) | 13% (n=78, p=0.25) |
| never learns | fixed | ≤ 1 | 9% (n=45, p=0.67) | 12% (n=41, p=0.39) | 11% (n=44, p=0.45) |
| never learns | adaptive | ≤ 5 | 10% (n=78, p=0.52) | 11% (n=74, p=0.46) | 10% (n=77, p=0.51) |
| never learns | adaptive | ≤ 1 | 7% (n=43, p=0.82) | 13% (n=39, p=0.35) | 10% (n=42, p=0.62) |

Readable reference samples: EEG muscle 1800, movement 1787, EMG 1770 (of 1800).

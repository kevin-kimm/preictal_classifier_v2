# preictal_classifier_v2

Cross-patient seizure forecasting from scalp EEG. The software watches a continuous EEG signal and warns the user when a seizure is likely to begin within the next 30 minutes, at least 5 seconds before onset.

> **Research prototype.** This software is not a medical device, has not been clinically validated, and must not be used to make medical decisions.

**Status:** Deliverable 2 in progress · **Author:** Kevin Kim · **Predecessor:** [preictal_classifier (AuraSense v1)](https://github.com/kevin-kimm/preictal_classifier)

## Overview

preictal_classifier_v2 is a ground-up rebuild of the AuraSense seizure prediction algorithm, scoped as a Software as a Medical Device (SaMD) prototype. It reuses some public datasets from v1, but no code or models. The software has four components.

| Component | What it does |
|---|---|
| Signal harmonization | Loads Siena, CHB-MIT and TUSZ recordings and converts them to one format: modern 10-20 channel names, a common sampling rate, and 18 bipolar derivations (the "double banana" montage). Using bipolar derivations also removes differences in reference electrode between datasets. Recordings using older labels (T3, T4, T5, T6) and newer labels (T7, T8, P7, P8) can then be used together. |
| Montage-agnostic classifier | Accepts whatever channels are available and scores each window as preictal, ictal or interictal. It works with any electrode layout, including the AuraSense headband and the OpenBCI Cyton. |
| Alarm logic | Converts the continuous risk score into discrete, non-repeating alarms, to limit alarm fatigue. |
| User interface | Runs locally. Replays dataset recordings or streams live Cyton data, showing the EEG, risk score, alarms and alarm times. |

## Key results

* **Prediction across patients doesn't work.** A model trained on other people and tested on someone new is at or near chance from brain waves alone (AUROC 0.556 in D1; 0.614 in D2, almost all of it from the time of day).
* **Personalization works.** A model that also learns the person's own earlier seizures does clearly better, and the gain held on every dataset.
* **The final test was on new patients with wearable EEG.** On 62 sealed SeizeIT2 patients with behind-the-ear sensors, the frozen design reached AUROC 0.621 (95% CI 0.564–0.671) against 0.547 without personal data. Its alarms warned 38% of seizures at 5.83 false alarms per 24 h, more than 3 times chance.
* **A device that keeps learning its wearer predicts better over time,** but its alarm thresholds need to keep adapting too: false alarms rose to 13.8 per 24 h.
* **It isn't a usable warning device yet.** The course target (80% of seizures at ≤ 5 false alarms per 24 h) was not met. The evidence points to a continuously personalizing device as the way forward; see the [D2 final analysis](docs/final_analysis.md).

## Intended use (draft)

*Software that analyzes continuous scalp EEG from a person with epilepsy and alerts that person when a seizure is likely to begin within the next 30 minutes and at least 5 seconds before onset, so they can move to a safe place or follow their seizure action plan.*

As a provisional SaMD framing under the IMDRF risk categorization, the output drives an immediate user action in a condition that is at least serious, which would place it in Category II or higher. This framing guides the design and the rigor of verification for a course project; it is not a regulatory determination.

Development follows design-control practices in a lightweight form. Requirements and pass/fail criteria are written and committed in the [verification test plan](docs/verification_plan.md) before any testing, and every result is traced back to that plan.

## Key definitions

| Term | Definition |
|---|---|
| Preictal | 30 min to 5 s before seizure onset: the period in which a correct warning must arrive |
| Seizure prediction horizon | 5 s, the minimum warning time |
| Ictal | Seizure onset to offset, from expert annotations |
| Interictal | At least 4 h away from any seizure (see [Defining normal EEG](#defining-normal-eeg-why-a-4-hour-gap)) |
| Alarm | A discrete warning, followed by a 30 min period in which no new alarm is raised |
| True alarm | An alarm followed by a seizure onset 5 s to 30 min later |

Full rules, including edge cases such as clustered seizures and gaps in recordings, are in Section 3 of the [verification plan](docs/verification_plan.md).

## Defining normal EEG: why a 4-hour gap

To count false alarms fairly, the software needs stretches of EEG that are clearly normal: far enough from any seizure that nothing seizure-related is going on. Here, "normal" (interictal) means at least 4 hours from any seizure, before or after. Everything between that gap and the 30-minute warning window is left out of training and testing.

The gap guards against two things:

* **After a seizure,** brain activity can stay slowed for minutes to hours while the brain recovers.
* **Before a seizure,** changes may start earlier than the 30-minute warning window in some people.

Labeling either as normal would distort the results. The choice is a research convention, not a rule of machine learning, and published studies vary:

| Gap | Normal EEG available | Risk of mislabeling | Where it's used |
|---|---|---|---|
| 1 h | Most | Highest: some post-seizure recovery, and possibly early pre-seizure changes, may count as normal | Less conservative studies |
| 2 h | More | Moderate | A middle ground |
| **4 h** | Least | Lowest | The Kaggle and Melbourne seizure-prediction competitions and many CHB-MIT studies (this project) |

The 4-hour gap was fixed in the [verification plan](docs/verification_plan.md) before any testing. Because definitions like this are sometimes chosen after seeing results, it stays fixed for the main results.

**What a shorter gap would change.** `scripts/gap_whatif.py` counts labels under different gaps, without training or testing anything:

| Gap | CHB-MIT normal EEG | Siena normal EEG | Siena test patients | Patients for the personalized test (CHB-MIT + Siena) |
|---|---|---|---|---|
| 1 h | 766 h | 75 h | 13 | 22 + 11 = 33 |
| 2 h | 675 h | 39 h | 4 | 21 + 3 = 24 |
| 4 h | 564 h | 22 h | 4 | 20 + 3 = 23 |

A 2-hour gap adds almost nothing, while a 1-hour gap would triple the number of testable Siena patients, because Siena's seizures come close together. (The personalized runs used 22 patients at 4 hours rather than 23, because they count normal EEG in 30-second windows, so one patient sits just under the 1-hour minimum.)

**Plan.**

* **Main results:** the main results, including the final test on SeizeIT2, keep the 4-hour gap.
* **1-hour sensitivity analysis:** after the final design is frozen, it will be tested once with a 1-hour gap on CHB-MIT and Siena and reported alongside, to show whether the conclusions depend on this choice.
* **Possible later experiment:** training with the extra normal EEG a 1-hour gap provides, while testing only against the 4-hour definition.

A plain-language explanation with figures is in [`docs/notes/normal_EEG_gap.pdf`](docs/notes/normal_EEG_gap.pdf).

## Datasets

The datasets are not included in this repository. Each has its own data use terms.

| Dataset | Version | Role | Subjects | Sampling rate | Montage |
|---|---|---|---|---|---|
| Siena Scalp EEG Database | 1.0.0 | Training and LOPO testing | 14 adults with epilepsy | 512 Hz | Referential |
| CHB-MIT Scalp EEG Database | 1.0.0 | Training and LOPO testing | 24 cases from 23 subjects, mostly pediatric | 256 Hz | Bipolar |
| TUH EEG Seizure Corpus (TUSZ) | 2.0.6 | False alarm testing in D1 (no usable preictal data, see below); adding it to training is a D2 experiment | 675 patients | Varies | Referential |
| TUH EEG Artifact Corpus (TUAR) | 3.0.1 | Artifact robustness testing | 213 patients | Varies | Referential |
| EEG During Mental Arithmetic Tasks | 1.0.0 | False alarm testing in people without epilepsy | 36 healthy subjects | 500 Hz | Referential |
| SeizeIT2 | 1.1.0 | Sealed final test (100 patients); 25 patients for development | 125 patients with focal epilepsy | See audit | Behind-the-ear wearable (2–3 channels) |

The counts below come from the data audit (verification test VT-01, [`results/d1/data_audit.md`](results/d1/data_audit.md)), not from the dataset papers.

| Dataset | Patients | EDF recordings | Hours | Annotated seizures |
|---|---|---|---|---|
| CHB-MIT | 24 cases (23 subjects) | 686 | 982.9 | 198 |
| Siena | 14 | 41 | 141.0 | 47 |
| TUSZ | 675 | 8,140 | 1,474.8 | 2,664 |
| TUAR | 213 | 310 | 100.0 | 161 (not used for prediction) |
| Mental arithmetic | 36 | 72 | 2.4 | 0 |

In CHB-MIT, cases chb01 and chb21 come from the same person and are treated as one patient in cross-patient splits.

TUSZ can't be used for prediction: its start times are anonymized and its files are at most 30 minutes long, so no TUSZ seizure has its 30-minute lead-up recorded (finding F-13 in the [D1 results](docs/verification_results/D1.md)). It is used for false alarm testing instead. After labeling, 25 patients can be test patients: 21 from CHB-MIT and 4 from Siena.

### SeizeIT2: data kept for the final test

SeizeIT2 (OpenNeuro ds005873, CC0 licence) is wearable data from 125 patients with focal epilepsy, recorded with behind-the-ear EEG plus ECG, EMG and movement sensors during hospital monitoring. It was downloaded on 2026-09-28 (24,877 files, 117.2 GiB) and is kept sealed as a **lockbox**: data that plays no part in designing the model and is used once, at the end, to test the frozen design. That gives one result free of the optimism that builds up when many ideas are tried on the same development data.

**What may be looked at before the freeze** is limited and recorded in Section 12 of the [evaluation methods](docs/evaluation_methods.md). A blind audit (`scripts/audit_seizeit2.py`, report in [`results/lockbox/seizeit2_feasibility.md`](results/lockbox/seizeit2_feasibility.md)) read only file listings, EDF headers and annotation column names, and reported seizure numbers only as dataset totals. It found:

* all 11,009 EDF files readable;
* 11,626 h of EEG on the `BTEleft SD`, `BTEright SD` and `CROSStop SD` channels;
* 883 seizures, with 97 patients having at least two;
* every EEG file starting at 00:00:00. The clock times are anonymized, so the design tested on SeizeIT2 can't use the time of day.

**Split.** SeizeIT2 is split once, at random from patient IDs only (seed 0, `scripts/split_seizeit2.py`, saved in `configs/seizeit2_split.yaml`):

* **25 patients for development:** building and checking the behind-the-ear adapter;
* **100 patients sealed as the lockbox.**

### Getting the data

Place each dataset in `data/raw/` using these folder names:

```
data/raw/
├── chbmit_v1.0.0/
├── siena_v1.0.0/
├── tusz_v2.0.6/
├── tuar_v3.0.1/
└── mental_arith_v1.0.0/
```

CHB-MIT, Siena and the mental arithmetic dataset are available from [PhysioNet](https://physionet.org). The TUH corpora require an access request to the [Neural Engineering Data Consortium](https://isip.piconepress.com/projects/nedc/html/tuh_eeg/). After approval and SSH key registration, TUSZ is downloaded with:

```bash
rsync -auvxL -e "ssh -i ~/.ssh/id_ed25519" \
  nedc-tuh-eeg@www.isip.piconepress.com:data/tuh_eeg/tuh_eeg_seizure/v2.0.6/ data/raw/tusz_v2.0.6/
```

The whole `data/` folder is excluded from Git by `.gitignore`.

## Repository structure

```
preictal_classifier_v2/
├── configs/
│   └── default.yaml          # All pipeline parameters in one place
├── data/                     # Not tracked by Git
│   ├── raw/                  # Datasets exactly as downloaded
│   ├── interim/              # Harmonized recordings
│   ├── processed/            # Labeled windows ready for training
│   └── models/               # Trained model checkpoints
├── docs/
│   ├── verification_plan.md  # Written and frozen before testing
│   └── verification_results/ # One report per deliverable
├── notebooks/                # Exploration only; not imported by src/
├── results/                  # Metric summaries
├── scripts/                  # Command-line entry points
│   ├── audit_data.py
│   ├── build_dataset.py
│   └── run_lopo.py
├── src/preictal/             # Installable Python package
│   ├── data/                 # loaders.py, harmonize.py, labels.py
│   ├── features/             # build_features.py
│   ├── models/               # model.py, train.py
│   ├── alarm/                # alarm.py
│   ├── evaluation/           # lopo.py, metrics.py
│   ├── live/                 # cyton.py
│   └── ui/                   # app.py
├── tests/                    # Automated verification tests (pytest)
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Setup

Requires Python 3.10 or later on macOS or Linux.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

`pip install -e .` installs the `preictal` package in editable mode, so scripts, notebooks and tests all import the same code from `src/preictal/`.

## Pipeline

| Stage | Code | Status |
|---|---|---|
| 1. Data audit | `scripts/audit_data.py` | Done (VT-01 passed) |
| 2. Harmonization | `src/preictal/data/harmonize.py` | Done (VT-02 to VT-05 passed) |
| 3. Relabeling | `src/preictal/data/labels.py` | Done (VT-06, VT-07 passed) |
| 4. Features (v1 and v2) | `src/preictal/features/` | Done |
| 5. Model, cross-patient training and evaluation | `src/preictal/models/`, `src/preictal/evaluation/`, `scripts/run_lopo.py`, `scripts/run_d2.py` | Done (D1, D2) |
| 6. Alarm logic | `src/preictal/alarm/alarm.py` | Done (VT-16 passed) |
| 7. Personalized designs and the frozen design | `scripts/run_personalized.py`, `scripts/run_personalized_alarms.py` | Done (frozen, tag `freeze-v1.13`) |
| 8. SeizeIT2 adapter and lockbox | `src/preictal/data/seizeit2.py`, `scripts/extract_seizeit2.py`, `scripts/run_seizeit2.py` | Done (final test reported) |
| 9. Continuous-personalization simulation | `src/preictal/evaluation/learning_curve.py`, `scripts/run_learning_curve.py` | Done |
| 10. Replay and live interface | `scripts/cyton_check.py` (connection check); interface to come | D3 |

Tunable parameters, including the preictal window, sampling rate, alarm refractory period and random seeds, are read from `configs/default.yaml`. Parameters fixed by the verification plan are marked there.

## Evaluation protocol

Personalized designs are evaluated by leaving one seizure out at a time within each patient, with buffers so that nothing near the test seizure is trained on. Choices between designs were made by nested selection or by rules fixed in advance, and the final design was tested once on sealed data (the SeizeIT2 lockbox). Cross-patient models are evaluated with leave-one-patient-out (LOPO) validation over the 25 eligible test patients: each patient is scored by a model that never saw any of their data. D1 models are trained on CHB-MIT and Siena. The full setup, fixed before any model was trained, is in [`docs/evaluation_methods.md`](docs/evaluation_methods.md). If the number of eligible patients makes LOPO impractical on a laptop, patient-grouped 10-fold cross-validation is used instead, under a rule fixed in advance (decision D-6 in the verification plan). Five random seeds are fixed in advance and all five are reported. Alarm thresholds are chosen on a validation subset of the training patients only, never on the test patient.

Window-level performance is measured by AUROC (preictal vs interictal) and a three-class confusion matrix. Event-level performance is measured by the fraction of seizures warned in time, false alarms per 24 hours, time spent in warning, and warning time, and is compared with a random predictor raising alarms at the same rate. Exact definitions and pass/fail criteria are in the [verification plan](docs/verification_plan.md).

## Tests

187 automated tests run with `python -m pytest -q` from the repository root (about 5 seconds). They cover:

* EDF reading and channel harmonization;
* labeling rules and timelines;
* features (checked against known signals and `scipy.signal.welch`);
* the alarm logic (VT-16);
* fold construction and leakage checks (VT-08);
* metric definitions;
* the patient-specific and forward-in-time splits, including that nothing from the future is trained on;
* the neural network (with a numerical gradient check);
* the SeizeIT2 adapter.

Long verification runs have their own scripts and write their evidence to `results/`. The README itself is checked by `scripts/check_readme.py` (VT-20).

## Verification and results

| Deliverable | Verification report | Status |
|---|---|---|
| 1. Rebuild and first evaluation | [`docs/verification_results/D1.md`](docs/verification_results/D1.md) | VT-01 to VT-14 complete (VT-13 failed) |
| 2. Final prototype with alarm logic | [`docs/verification_results/D2.md`](docs/verification_results/D2.md) | VT-15 and VT-17 failed, VT-16 passed; patient-specific test reported |
| 3. Interface and live Cyton test | `docs/verification_results/D3.md` | Not started |

### Current model metrics

| Metric | D1 | D2 | D3 (live) |
|---|---|---|---|
| Mean LOPO AUROC (± SD across seeds) | 0.556 ± 0.007 (95% CI 0.502–0.616) | 0.614 ± 0.007 (0.528 without time of day) | – |
| Clock-only baseline AUROC | 0.697 (seed 0) | 0.691 | Not applicable |
| Patient-specific AUROC (22 patients, EEG only) | – | 0.662 (95% CI 0.588–0.742) | Not applicable |
| **Frozen personalized design** (general + personal, no time of day), AUROC on development data | – | 0.700 (95% CI 0.630–0.768; optimistic, chosen on these patients) | Not applicable |
| Frozen design alarms, target ≤ 5 / ≤ 1 false alarms per 24 h | – | 16% warned at 3.43 per 24 h (chance 7%) / 9% at 1.41 (chance 3%) | – |
| **Final test: SeizeIT2 lockbox, frozen design AUROC (62 new patients)** | – | **0.621 (95% CI 0.564–0.671); other patients only 0.547** | – |
| **Final test: SeizeIT2 lockbox alarms, ≤ 5 / ≤ 1 per 24 h (20 random patients)** | – | **38% warned at 5.83 per 24 h (chance 11%) / 18% at 1.69 (chance 3.5%)** | – |
| Event sensitivity | 0.21 (chance at this rate: 0.20) | 0.16 (chance: 0.11) | Not applicable |
| False alarms per 24 h, test patients | 10.61 | 5.84 | – |
| False alarms per 24 h, TUSZ (unseen patients) | 69.67 | 55.2 (held-out half) | – |
| Time in warning, median warning time | see [`lopo_report.md`](results/d1/lopo_report.md) | see [`d2_report.md`](results/d2/d2_report.md) | Not applicable |

D1 is a deliberately simple, untuned baseline. It detects seizures well (AUROC 0.865 for windows inside a seizure) but predicts them only slightly better than chance, and a model that knows only the time of day does better (see findings F-18 to F-23 in the [D1 results](docs/verification_results/D1.md)). D2 tried normalization, context, time of day, TUSZ data and a neural network, chosen per patient by nested cross-validation. Its gain over D1 came entirely from the time of day, and its alarms stayed near chance. Trained on the same person's other seizures, though, the D1 model reaches 0.662 from EEG alone, which points to a personalized design (findings F2-01 to F2-05 in the [D2 results](docs/verification_results/D2.md)).

**Personalized designs.** A series of pre-planned tests on the 22 patients with at least two seizures found that brain waves become predictive only once the model has seen the person:

* **Without the time of day,** a model trained on other people is at chance (0.529), while adding the person's own data raises it to 0.681, improving 19 of 22 patients.
* **Changes that didn't help:** richer features, longer context, more cautious trees and more normal training EEG.
* **The frozen design** (general + personal, feature set v2, personal baseline, 10 min context, no time of day; Git tag `freeze-v1.13`) warns about 2–3 times as many seizures as random alarms. That is a real signal, but far from a usable warning device.

It will be tested once on 100 sealed SeizeIT2 patients (findings F2-07 to F2-15).

A planned sensitivity analysis with a 1-hour gap for normal EEG lowered the frozen design's score on the same 22 patients (0.700 → 0.649), while 11 patients who become testable only under that looser definition scored 0.794. The choice of gap therefore matters by about 0.05, and the 4-hour result stays the main one (F2-15).

**SeizeIT2 dry run.** On 14 SeizeIT2 development patients (behind-the-ear wearable EEG), the frozen design replicated the personalization finding (other patients only 0.516; general + personal 0.669, better for 13 of 14 patients) and warned 46% of seizures at 4.6 false alarms per 24 h. The 100 sealed lockbox patients will give the deciding result (F2-16).

**Final test (SeizeIT2 lockbox).** On 62 patients the design never saw, the frozen design reached AUROC 0.621 (95% CI 0.564–0.671), against 0.547 for a model trained only on other people. Its alarms warned 38% of seizures at 5.8 false alarms per 24 h, more than 3 times chance. The signal is real but modest, and personal: learning the wearer's own seizures is what makes it work (F2-17).

**A device that keeps learning.** Simulated forward in time on the SeizeIT2 development patients, a device that retrains after each of the wearer's seizures predicted better than one that never learns (AUROC 0.606 against 0.454 on the same periods; better in 26 of 31, p = 0.0015). It warned 38% of seizures against 16%, but at 13.8 false alarms per 24 h, so alarm thresholds would need to keep adapting too (F2-18).

## Comparison with v1

| Aspect | v1 (AuraSense, final version v6) | v2 |
|---|---|---|
| Datasets | Siena (12 evaluable patients); EEGMMIDB for false alarm testing | CHB-MIT and Siena for development; TUSZ and mental arithmetic for false alarms; SeizeIT2 sealed for the final test |
| Labels | preictal 0–5 min before onset; normal more than 30 min from a seizure | preictal 30 min to 5 s before onset; normal at least 4 h from any seizure |
| Model | dense neural network on 64 band-power features (Keras, TensorFlow Lite export) | gradient boosting on pooled, montage-agnostic features; personalized design (general + personal) frozen for the final test |
| Evaluation | leave one patient out; best of 297 seeds kept per patient using that patient's test AUC | leave one patient out with pre-set seeds and inner validation; leave one seizure out for the personalized design; sealed final test |
| Headline result | mean AUC 0.713 (single run 0.568) | cross-patient 0.556 (D1); personalized 0.700 on development data |
| Verification | false alarm rate evaluation | pre-registered verification plan and evaluation methods with pass/fail criteria |

**Why the headline numbers differ.** v6's single run (0.568) agrees with v2's cross-patient baseline (0.556). Its reported 0.713 comes from keeping, for each patient, the best of 297 random seeds judged on that patient's own test results. A simulation (`scripts/demo_best_of_seeds.py`) shows that luck alone produces that number, with no real improvement. A new wearer has no seizures to pick a seed from, so it isn't achievable in practice. v6's proposed patient-specific fine-tuning, meanwhile, matches v2's main finding that personalization is what works. Details are in VT-14 and findings F-25 to F-27 of the [D1 results](docs/verification_results/D1.md).

## Roadmap

| Deliverable | Item | Weight | Status |
|---|---|---|---|
| 1 (40%) | Evaluation methods: seeds, threshold derivation, alarm logic, relabeling | 10% | Written ([evaluation_methods.md](docs/evaluation_methods.md)) |
| 1 | Harmonized loader for Siena, CHB-MIT and TUSZ | 10% | Done |
| 1 | Relabeled corpus (30 min to 5 s before onset) | 5% | Done |
| 1 | Cross-patient LOPO classifier | 5% | Done (VT-11 passed narrowly) |
| 1 | Verification test plan, written before testing | 5% | Done (frozen, tag `vtp-1.0`) |
| 1 | Verification results against the plan | 5% | VT-01 to VT-14 done |
| 1 | Detailed comparison with v1 | – | Done (VT-14) |
| 2 (40%) | Classifier improved by at least 15% over D1 | 10% | Not met: +10.5%, all from the time of day |
| 2 | Alarm generation logic | 5% | Done (VT-16 passed) |
| 2 | Event sensitivity and false alarm targets | – | Not met: 16% warned at 5.84 false alarms per 24 h |
| 2 | Personalized designs and final development round (added) | – | Done; design frozen (`freeze-v1.13`) |
| 2 | SeizeIT2 lockbox test of the frozen design (added) | – | Done: AUROC 0.621, alarms 38% at 5.83 per 24 h |
| 2 | Continuous-personalization simulation (added) | – | Done (F2-18) |
| 2 | Final analysis of results | 10% | Done ([final_analysis.md](docs/final_analysis.md)) |
| 2 | README | 15% | Checked by `scripts/check_readme.py` (VT-20) |
| 3 (20%) | Local interface showing dataset replay and alarms | 10% | Not started |
| 3 | Real-time Cyton acquisition, live baseline, seizure-free recording | – | Not started |
| 3 | Analysis report compared with D1 and D2 | 10% | Not started |

## Known limitations

These are known before testing and will be revisited in the final analysis. TUSZ recordings are short and their start times anonymized, so no TUSZ seizure has a usable preictal period; TUSZ is used only for false alarm testing in D1. Only 25 patients (21 CHB-MIT, 4 Siena) can be test patients, so results rest on a small group dominated by children's recordings. CHB-MIT is pediatric and recorded in a bipolar montage, which constrains the common representation for all datasets. Seizure onsets come from expert annotations, which carry their own uncertainty. The datasets were recorded with clinical equipment in hospital settings, which differs from a consumer headband. Only 2–10 seizures per patient are available for personalization, which appears to be the main limit on accuracy. SeizeIT2's clock times are anonymized, so its recordings are placed back to back in run order, with preictal windows taken only from the seizure's own file. In CHB-MIT and Siena, the time of day alone separates preictal from interictal periods better than the D1 EEG model, so EEG results must be compared with a clock-only baseline, not just with 0.5. Live tests use seizure-free recordings, so they can measure false alarms but not whether seizures are predicted. The 4-hour gap that defines normal EEG leaves only 4 Siena patients testable across patients and 3 in the personalized test; a 1-hour gap would allow 13 and 11, at a higher risk of mislabeling (see [Defining normal EEG](#defining-normal-eeg-why-a-4-hour-gap)). The mental arithmetic recordings total only 2.4 h, which is too short to estimate a false alarm rate; they are used to check that task-related EEG changes don't trigger alarms.

## Citations

If you use this work, also cite the datasets. Check each dataset's page for its exact required citation.

Shoeb, A. H. (2009). *Application of machine learning to epileptic seizure onset detection and treatment.* PhD thesis, Massachusetts Institute of Technology.

Detti, P., Vatti, G., & Zabalo Manrique de Lara, G. (2020). EEG synchronization analysis for seizure prediction: A study on data of noninvasive recordings. *Processes*, 8(7), 846.

Shah, V., von Weltin, E., Lopez, S., McHugh, J. R., Veloso, L., Golmohammadi, M., Obeid, I., & Picone, J. (2018). The Temple University Hospital Seizure Detection Corpus. *Frontiers in Neuroinformatics*, 12, 83.

Obeid, I., & Picone, J. (2016). The Temple University Hospital EEG Data Corpus. *Frontiers in Neuroscience*, 10, 196.

Hamid, A., Gagliano, K., Rahman, S., Tulin, N., Tchiong, V., Obeid, I., & Picone, J. (2020). The Temple University Artifact Corpus: An annotated corpus of EEG artifacts. *IEEE Signal Processing in Medicine and Biology Symposium (SPMB)*.

Zyma, I., Tukaev, S., Seleznov, I., Kiyono, K., Popov, A., Chernykh, M., & Shpenkov, O. (2019). Electroencephalograms during mental arithmetic task performance. *Data*, 4(1), 14.

Bhagubai, M., Chatzichristos, C., Swinnen, L., et al. (2025). SeizeIT2: Wearable dataset of patients with focal epilepsy. *arXiv preprint* arXiv:2502.01224.

Brinkmann, B. H., et al. (2016). Crowdsourcing reproducible seizure forecasting in human and canine epilepsy. *Brain*, 139(6), 1713–1722.

Goldberger, A. L., et al. (2000). PhysioBank, PhysioToolkit, and PhysioNet: Components of a new research resource for complex physiologic signals. *Circulation*, 101(23), e215–e220.

## License

The code is released under the license in [LICENSE](LICENSE). The datasets are distributed under their own terms and are not redistributed here.

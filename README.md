# preictal_classifier_v2

Cross-patient seizure forecasting from scalp EEG. The software watches a continuous EEG signal and warns the user when a seizure is likely to begin within the next 30 minutes, at least 30 seconds before onset so there is time to act.

> **Research prototype.** This software is not a medical device, has not been clinically validated, and must not be used to make medical decisions.

**Status:** Deliverable 1 in progress · **Author:** Kevin Kim · **Predecessor:** [preictal_classifier (AuraSense v1)](https://github.com/kevin-kimm/preictal_classifier)

## Overview

preictal_classifier_v2 is a ground-up rebuild of the AuraSense seizure prediction algorithm, scoped as a Software as a Medical Device (SaMD) prototype. It reuses some public datasets from v1, but no code or models. The software has four components.

| Component | What it does |
|---|---|
| Signal harmonization | Loads Siena, CHB-MIT and TUSZ recordings and converts them to one format: modern 10-20 channel names, a common sampling rate and a common montage. Recordings using older labels (T3, T4, T5, T6) and newer labels (T7, T8, P7, P8) can then be used together. |
| Montage-agnostic classifier | Accepts whatever channels are available and scores each window as preictal, ictal or interictal. It works with any electrode layout, including the AuraSense headband and the OpenBCI Cyton. |
| Alarm logic | Converts the continuous risk score into discrete, non-repeating alarms, to limit alarm fatigue. |
| User interface | Runs locally. Replays dataset recordings or streams live Cyton data, showing the EEG, risk score, alarms and alarm times. |

## Intended use (draft)

*Software that analyzes continuous scalp EEG from a person with epilepsy and alerts that person when a seizure is likely to begin within the next 30 minutes, at least 30 seconds before onset, so they can move to a safe place or follow their seizure action plan.*

As a provisional SaMD framing under the IMDRF risk categorization, the output drives an immediate user action in a condition that is at least serious, which would place it in Category II or higher. This framing guides the design and the rigor of verification for a course project; it is not a regulatory determination.

Development follows design-control practices in a lightweight form. Requirements and pass/fail criteria are written and committed in the [verification test plan](docs/verification_plan.md) before any testing, and every result is traced back to that plan.

## Key definitions

| Term | Definition |
|---|---|
| Preictal | 30 min to 30 s before seizure onset: the period in which a correct warning must arrive |
| Seizure prediction horizon | 30 s, the minimum warning time |
| Ictal | Seizure onset to offset, from expert annotations |
| Interictal | At least 4 h away from any seizure |
| Alarm | A discrete warning, followed by a 30 min period in which no new alarm is raised |
| True alarm | An alarm followed by a seizure onset 30 s to 30 min later |

Full rules, including edge cases such as clustered seizures and gaps in recordings, are in Section 3 of the [verification plan](docs/verification_plan.md).

## Datasets

The datasets are not included in this repository. Each has its own data use terms.

| Dataset | Version | Role | Subjects | Sampling rate | Montage |
|---|---|---|---|---|---|
| Siena Scalp EEG Database | 1.0.0 | Training and LOPO testing | 14 adults with epilepsy | 512 Hz | Referential |
| CHB-MIT Scalp EEG Database | 1.0.0 | Training and LOPO testing | 22 pediatric subjects (23 cases) | 256 Hz | Bipolar |
| TUH EEG Seizure Corpus (TUSZ) | 2.0.6 | Training and LOPO testing | From data audit | Varies | Referential |
| TUH EEG Artifact Corpus (TUAR) | 3.0.1 | Artifact robustness testing | From data audit | Varies | Referential |
| EEG During Mental Arithmetic Tasks | 1.0.0 | False alarm testing in people without epilepsy | 36 healthy subjects | 500 Hz | Referential |

Seizure counts and recording hours per dataset will be added from the data audit (verification test VT-01), so the numbers in this README come from the data actually used rather than from the dataset papers.

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
| 1. Data audit | `scripts/audit_data.py` | Planned |
| 2. Harmonization | `src/preictal/data/harmonize.py` | Planned |
| 3. Relabeling | `src/preictal/data/labels.py` | Planned |
| 4. Model and LOPO training | `src/preictal/models/`, `src/preictal/evaluation/lopo.py` | Planned |
| 5. Alarm logic | `src/preictal/alarm/alarm.py` | Planned |
| 6. Replay and live interface | `src/preictal/ui/app.py`, `src/preictal/live/cyton.py` | Planned |

Tunable parameters, including the preictal window, sampling rate, alarm refractory period and random seeds, are read from `configs/default.yaml`. Parameters fixed by the verification plan are marked there.

## Evaluation protocol

Models are evaluated with cross-patient leave-one-patient-out (LOPO) validation: each patient is scored by a model that never saw any of their data. Five random seeds are fixed in advance and all five are reported. Alarm thresholds are chosen on a validation subset of the training patients only, never on the test patient.

Window-level performance is measured by AUROC (preictal vs interictal) and a three-class confusion matrix. Event-level performance is measured by the fraction of seizures warned in time, false alarms per 24 hours, time spent in warning, and warning time, and is compared with a random predictor raising alarms at the same rate. Exact definitions and pass/fail criteria are in the [verification plan](docs/verification_plan.md).

## Verification and results

| Deliverable | Verification report | Status |
|---|---|---|
| 1. Rebuild and first evaluation | `docs/verification_results/D1.md` | Not started |
| 2. Final prototype with alarm logic | `docs/verification_results/D2.md` | Not started |
| 3. Interface and live Cyton test | `docs/verification_results/D3.md` | Not started |

### Current model metrics

| Metric | D1 | D2 | D3 (live) |
|---|---|---|---|
| Mean LOPO AUROC (± SD across seeds) | – | – | – |
| Event sensitivity | – | – | Not applicable |
| False alarms per 24 h | – | – | – |
| Time in warning | – | – | – |
| Median warning time | – | – | Not applicable |

## Comparison with v1

| Aspect | v1 (AuraSense) | v2 |
|---|---|---|
| Datasets | Siena; EEGMMIDB for false alarm testing | Siena, CHB-MIT, TUSZ; TUAR and mental arithmetic for robustness and false alarm testing |
| Model | Feature extraction with Keras models, TensorFlow Lite export | Montage-agnostic classifier (to be documented in D1) |
| Evaluation split | To be filled in from v1 | Cross-patient LOPO |
| Alarm logic | To be filled in from v1 | Non-repeating alarms with 30 min refractory period |
| Verification | False alarm rate evaluation | Pre-registered verification plan with pass/fail criteria |

A detailed comparison, including results, is part of the Deliverable 1 verification report.

## Roadmap

| Deliverable | Item | Weight | Status |
|---|---|---|---|
| 1 (40%) | Evaluation methods: seeds, threshold derivation, alarm logic, relabeling | 10% | In progress |
| 1 | Harmonized loader for Siena, CHB-MIT and TUSZ | 10% | Not started |
| 1 | Relabeled corpus (30 min to 30 s before onset) | 5% | Not started |
| 1 | Cross-patient LOPO classifier | 5% | Not started |
| 1 | Verification test plan, written before testing | 5% | Draft |
| 1 | Verification results against the plan | 5% | Not started |
| 1 | Detailed comparison with v1 | – | Not started |
| 2 (40%) | Classifier improved by at least 15% over D1 | 10% | Not started |
| 2 | Alarm generation logic | 5% | Not started |
| 2 | Event sensitivity and false alarm targets | – | Not started |
| 2 | Final analysis of results | 10% | Not started |
| 2 | README | 15% | In progress |
| 3 (20%) | Local interface showing dataset replay and alarms | 10% | Not started |
| 3 | Real-time Cyton acquisition, live baseline, seizure-free recording | – | Not started |
| 3 | Analysis report compared with D1 and D2 | 10% | Not started |

## Known limitations

These are known before testing and will be revisited in the final analysis. Many TUSZ recordings are short clinical sessions, so a large share of TUSZ seizures may not have a full 30 min preictal period recorded. CHB-MIT is pediatric and recorded in a bipolar montage, which constrains the common representation for all datasets. Seizure onsets come from expert annotations, which carry their own uncertainty. The datasets were recorded with clinical equipment in hospital settings, which differs from a consumer headband. Live tests use seizure-free recordings, so they can measure false alarms but not whether seizures are predicted.

## Citations

If you use this work, also cite the datasets. Check each dataset's page for its exact required citation.

Shoeb, A. H. (2009). *Application of machine learning to epileptic seizure onset detection and treatment.* PhD thesis, Massachusetts Institute of Technology.

Detti, P., Vatti, G., & Zabalo Manrique de Lara, G. (2020). EEG synchronization analysis for seizure prediction: A study on data of noninvasive recordings. *Processes*, 8(7), 846.

Shah, V., von Weltin, E., Lopez, S., McHugh, J. R., Veloso, L., Golmohammadi, M., Obeid, I., & Picone, J. (2018). The Temple University Hospital Seizure Detection Corpus. *Frontiers in Neuroinformatics*, 12, 83.

Obeid, I., & Picone, J. (2016). The Temple University Hospital EEG Data Corpus. *Frontiers in Neuroscience*, 10, 196.

Hamid, A., Gagliano, K., Rahman, S., Tulin, N., Tchiong, V., Obeid, I., & Picone, J. (2020). The Temple University Artifact Corpus: An annotated corpus of EEG artifacts. *IEEE Signal Processing in Medicine and Biology Symposium (SPMB)*.

Zyma, I., Tukaev, S., Seleznov, I., Kiyono, K., Popov, A., Chernykh, M., & Shpenkov, O. (2019). Electroencephalograms during mental arithmetic task performance. *Data*, 4(1), 14.

Goldberger, A. L., et al. (2000). PhysioBank, PhysioToolkit, and PhysioNet: Components of a new research resource for complex physiologic signals. *Circulation*, 101(23), e215–e220.

## License

The code license is not yet chosen. The datasets are distributed under their own terms and are not redistributed here.

# AuraSense v3 scope: a personalized, adaptive seizure-warning algorithm

Kevin Kim · 2026-10-04 · written before any v3 evaluation on held-out patients

## 1. Why the scope changes

v2 tested cross-patient prediction rigorously, and it doesn't work from brain waves alone. A model trained on other people was at or near chance on every dataset (AUROC 0.53 on CHB-MIT and Siena, 0.52 on the SeizeIT2 development patients, 0.55 on the SeizeIT2 lockbox). What worked everywhere was learning the person's own seizures:

* **Lockbox:** 0.621 against 0.547 on 62 unseen patients.
* **Forward-in-time simulation:** 0.606 against 0.454 (`docs/verification_results/D2.md`, F2-07 to F2-18).

v3 is therefore designed as a base model that adapts to each wearer, not as one model for everyone.

## 2. Intended use (draft)

AuraSense v3 is software for a wearable EEG device. It starts from a base model, calibrates on the wearer's normal EEG, learns from the wearer's own confirmed seizures, and then warns that a seizure is likely within the next 30 minutes. It is an adjunct that helps people with epilepsy and their caregivers prepare. It isn't intended to diagnose epilepsy, detect seizures in progress, or guide medication.

* **For:** people with frequent focal seizures (a working target of several per month) who will wear the device continuously and confirm their seizures.
* **Not for (yet):** people with rare seizures, since the device needs several seizures to learn from; anyone relying on it as their only safety measure; and the first period of use, before the device has learned at least one seizure.

## 3. How it works

1. **Calibration.** The device records the first hours of normal EEG to set the wearer's personal baseline. Until it has learned a seizure, it runs the base model, which is near chance, and it says so.
2. **Learning.** When a seizure is confirmed (by the wearer or a caregiver, or later by automatic detection with confirmation), the device retrains on everything it has recorded so far, using the v2 frozen recipe: base data plus the wearer's own data at half of each class's weight, feature set v2, 10 min context and a personal baseline.
3. **Threshold adaptation.** The alarm threshold is recalibrated regularly on the wearer's recent normal EEG. Adaptive thresholds cut false alarms by a quarter to a third (v3, F3-01). The first day after each seizure is the remaining problem (F3-02).
4. **Warnings.** Warnings are issued once at least one seizure has been learned. The performance before that point is reported separately.

## 4. Success criteria (Phase B, fixed now)

These apply to the learning device at the ≤ 5 setting, over all steps after at least one learned seizure, on the held-out patients (Section 5). All three must hold:

| | Criterion | Test |
|---|---|---|
| S1 | **It warns better than random alarms** at its observed false-alarm rate | one-sided binomial, p < 0.05 |
| S2 | **False alarms at most 5 per 24 h,** as observed | the measured rate |
| S3 | **Learning helps:** higher AUROC than the never-learning model on the same steps | Wilcoxon signed-rank, p < 0.05 |

Also reported, without pass or fail:

* the ≤ 1 setting;
* results by learning stage;
* results by time since retraining;
* the course target (80% of seizures warned at ≤ 5 false alarms per 24 h), for reference.

## 5. Data plan

| Use | Data |
|---|---|
| Base model | The 25 SeizeIT2 development patients (behind-the-ear EEG) |
| **Phase A, tuning:** choosing the device's settings (v1.22 onwards) | The same 25 development patients, forward in time |
| **Phase B, held-out evaluation:** run once, with the configuration from Phase A | The other 100 SeizeIT2 patients, forward in time |
| Scalp EEG (secondary) | CHB-MIT and Siena, 22 patients, forward in time |

**What Phase B's patients are.** They weren't used to develop v3, but they were used in v2's lockbox test of a different design. So Phase B is a held-out evaluation of v3, not an untouched one, and is reported that way.

**What the data can't show:**

* *Long-term behavior,* because hospital recordings last days, not months.
* *A truly untouched final test of v3.* Both would need new data, for example from AuraSense's own users.

## 6. Experiments, in order

Each experiment is written into `docs/evaluation_methods.md` with a decision rule before it runs.

1. **Threshold schedules (v1.22, Phase A):** faster recalibration, and a stricter first day after each seizure.
2. **Movement gating** using the wearable's accelerometer (F3-02 found false alarms twice as likely during high movement), reporting its cost in warned seizures.
3. **A warm-up rule:** when warnings switch on (after 1, 2 or 3 learned seizures).
4. **Per-channel features** for the personalized model (scalp and Cyton), since pooling erases where on the head changes happen.
5. **Heart-rate features** from SeizeIT2's ECG.
6. **A personal time prior** (CHB-MIT and Siena only; SeizeIT2's clock is anonymized).
7. **A small deep-learning model** of our own, pretrained on unlabeled EEG and compared head to head in the simulation.

Then **Phase B,** once.

## 7. Relationship to the course and to regulation

* **The course.** D1 and D2 (v2) are complete, and their results stand. v3 is post-D2 work. D3 (interface and live Cyton test) is paused, and will adopt this intended use when it resumes.
* **Regulation.** A device that retrains itself after release needs its changes specified and verified in advance, in the spirit of the FDA's approach to predetermined change control plans for AI-enabled devices. Sections 3 and 4 are a first draft of that specification.

# Responses to the D1 feedback

Kevin Kim · started 2026-10-26 · preictal_classifier_v2

The D1 report came back with comments from the course instructor. Each one is answered below with evidence, or with the experiment that answers it. The experiments were written into `docs/evaluation_methods.md` (v1.25, Section 14) before any of them was run. Rows marked *pending* are filled in from the results as they come in.

| # | Comment | How it is answered | Status |
|---|---|---|---|
| 1 | How does this compare with patients' ability to predict their own seizures (prodrome or aura)? The device would need to do better, or give more precise timing. | Literature (below), plus warning windows of 10–60 min scored with chance recomputed for each (Section 14.4) | Literature done; timing pending |
| 2 | Some patients may have a longer or shorter "true" preictal period. Change the amount of interictal time and see if accuracy changes. Try unsupervised learning. | Training preictal length 10–60 min, and chosen per patient (Section 14.2); interictal gap 1, 2, 4 and 8 h (Section 14.9); isolation-forest anomaly score with no seizure labels (Section 14.6) | Pending |
| 3 | Is 30 s sufficient? Infra-slow oscillations. | Check whether the amplifiers recorded below 0.5 Hz, then 5-minute infra-slow features as a challenger (Section 14.7) | Pending |
| 4 | If a window contains two states (e.g. a seizure starts at 22 s), how is it classified? Could edge cases hurt accuracy? | By design (below), plus a challenger trained without such windows and AUROC on test windows without them (Section 14.2) | Design answer done; experiment pending |
| 5 | Did you only use 25 people out of the datasets? | Below | Done |
| 6 | Seizure detection (0.865): surprised it isn't higher. Can you see the difference in the missed seizures? | Per-seizure detection scores and EEG of the best and worst detected seizures (Section 14.8) | Pending |
| 7 | PPV would be useful, and a confusion matrix. | PPV, NPV and confusion matrices for every alarm result, at hospital and home seizure rates (Sections 14.1, 14.5) | Pending |
| 8 | Surprised changing the seed has such a large effect with a larger dataset. | Seed variability per patient and overall (Section 14.1), and the explanation below | Explanation done; numbers pending |
| 9 | Fewer channels scoring higher: does that make sense? | Seed-by-seed and patient-by-patient test (Section 14.1) | Pending |

## 1. Patients' own warning signs

Prospective studies have tested whether people with epilepsy can foresee their seizures:

* **E-diary self-prediction.** In 19 adults with focal epilepsy and frequent seizures, patients' own predictions were linked to seizures in the following 6 h, and still within 12 h (multivariate odds ratio 2.84). The best predictors caught about half their seizures. Predictions were made over hours, not minutes ([Borkowski et al., 2013](https://stacks.cdc.gov/view/cdc/195437)).
* **Prodromes.** Of 500 patients interviewed at three epilepsy centres, about 6% reported prodromes at least 30 min before seizures. Followed prospectively, they predicted seizures no better than a random predictor, and some prodromes were recorded only after the seizure ([Maiwald et al., 2011](https://jeti.uni-freiburg.de/papers/YEBEH2581.pdf)).

So patients' own forecasting, where it works, is coarse: hours rather than a specific 30-minute window, and in only some patients. A device adds value if it beats chance over a 30-minute window, which the frozen design does (38% of seizures at 5.8 false alarms per 24 h, 3 times chance, on 20 new patients), or if it gives more precise timing. Auras, the first symptom of a focal seizure, are already part of the seizure and give seconds to a minute or two of warning; that is the lead time the device has to beat. The warning-window analysis (Section 14.4) shows how performance changes as the window narrows.

## 4. Windows that contain two states

Each 30 s window is labeled by the state at its **end** (evaluation methods, Section 2), and windows start every 5 s. Because preictal ends 5 s before onset and windows are labeled at their end:

* no preictal window contains any seizure EEG: the last one ends 5 s before onset;
* the first 6 windows of each preictal period begin up to 30 s earlier, in excluded time (30–30.5 min before onset);
* the first 6 windows labeled ictal contain mostly preictal EEG (up to 25 s of it). This affects the ictal class in training and seizure detection, which is why D1 reported detection both for all ictal windows (0.810) and for windows entirely inside a seizure (0.865);
* interictal windows are at least 4 h from any seizure, so they never contain another state's EEG.

The comment's example (a seizure starting 22 s into a window) is therefore an ictal window in training. The `pure` challenger removes all such windows from training, and every run reports how many there are.

## 5. Why 25 test patients

| Dataset | Patients | Used for | Why |
|---|---|---|---|
| CHB-MIT | 23 subjects (24 cases; chb01 and chb21 are one person) | Training: all. Testing: 21 | Testing needs at least one seizure with 90% of its 30 min lead-up recorded, and at least 1 h of EEG 4 h or more from any seizure |
| Siena | 14 | Training: all. Testing: 4 | Most Siena patients have no EEG 4 h or more from a seizure (13 would be testable with a 1 h gap) |
| TUSZ | 675 | False-alarm testing only | Files are at most 30 min long and their clock times are anonymized, so no seizure has a recorded 30 min lead-up |
| SeizeIT2 | 125 | 25 for development, 100 sealed for the final test (62 scored) | Added after D1 |

All 37 CHB-MIT and Siena subjects train the cross-patient model; 25 of them can be test patients. The personalized tests need two eligible seizures per patient, which leaves 22.

## 8. Why seeds mattered so much in v1

The seed changes how the model is trained (here, which training windows are held back to decide when to stop). With many patients, those changes mostly cancel out in the average: v2's mean AUROC moved by only about ±0.007 between seeds. But a single patient's AUROC rests on a few seizures, since windows from the same seizure are strongly correlated, so it can move by several hundredths between seeds. v1 trained 297 seeds and kept, for each test patient, the run that scored best on that patient's own test data. Keeping the best of 297 noisy draws pushes every patient up at once, which inflated the reported 0.713; a single run scored 0.568. The numbers for v2 (per-patient spread, and how much "best of 5 seeds" alone would inflate the mean) are in `results/d2_plus/existing_results.md`.

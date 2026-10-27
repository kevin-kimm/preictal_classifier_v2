# Responses to the D1 feedback

Kevin Kim · started 2026-10-26 · preictal_classifier_v2

The D1 report came back with comments from the course instructor. Each one is answered below with evidence, or with the experiment that answers it. The experiments were written into `docs/evaluation_methods.md` (v1.25, Section 14) before any of them was run. Rows marked *pending* are filled in from the results as they come in.

| # | Comment | How it is answered | Status |
|---|---|---|---|
| 1 | How does this compare with patients' ability to predict their own seizures (prodrome or aura)? The device would need to do better, or give more precise timing. | Literature (below), plus warning windows of 10–60 min scored with chance recomputed for each (Section 14.4) | Literature done; timing pending |
| 2 | Some patients may have a longer or shorter "true" preictal period. Change the amount of interictal time and see if accuracy changes. Try unsupervised learning. | Training preictal length 10–60 min, and chosen per patient (Section 14.2); interictal gap 1, 2, 4 and 8 h (Section 14.9); isolation-forest anomaly score with no seizure labels (Section 14.6) | Pending |
| 3 | Is 30 s sufficient? Infra-slow oscillations. | Check whether the amplifiers recorded below 0.5 Hz, then 5-minute infra-slow features as a challenger (Section 14.7) | Check done (below); challenger pending |
| 4 | If a window contains two states (e.g. a seizure starts at 22 s), how is it classified? Could edge cases hurt accuracy? | By design (below), plus a challenger trained without such windows and AUROC on test windows without them (Section 14.2) | Design answer done; experiment pending |
| 5 | Did you only use 25 people out of the datasets? | Below | Done |
| 6 | Seizure detection (0.865): surprised it isn't higher. Can you see the difference in the missed seizures? | Per-seizure detection scores and EEG of the best and worst detected seizures (Section 14.8) | Done |
| 7 | PPV would be useful, and a confusion matrix. | PPV, NPV and confusion matrices for every alarm result, at hospital and home seizure rates (Sections 14.1, 14.5) | Existing results done (below); new runs pending |
| 8 | Surprised changing the seed has such a large effect with a larger dataset. | Seed variability per patient and overall (Section 14.1), and the explanation below | Done |
| 9 | Fewer channels scoring higher: does that make sense? | Seed-by-seed and patient-by-patient test (Section 14.1) | Done |

## 1. Patients' own warning signs

Prospective studies have tested whether people with epilepsy can foresee their seizures:

* **E-diary self-prediction.** In 19 adults with focal epilepsy and frequent seizures, patients' own predictions were linked to seizures in the following 6 h, and still within 12 h (multivariate odds ratio 2.84). The best predictors caught about half their seizures. Predictions were made over hours, not minutes ([Borkowski et al., 2013](https://stacks.cdc.gov/view/cdc/195437)).
* **Prodromes.** Of 500 patients interviewed at three epilepsy centres, about 6% reported prodromes at least 30 min before seizures. Followed prospectively, they predicted seizures no better than a random predictor, and some prodromes were recorded only after the seizure ([Maiwald et al., 2011](https://jeti.uni-freiburg.de/papers/YEBEH2581.pdf)).

So patients' own forecasting, where it works, is coarse: hours rather than a specific 30-minute window, and in only some patients. A device adds value if it beats chance over a 30-minute window, which the frozen design does (38% of seizures at 5.8 false alarms per 24 h, 3 times chance, on 20 new patients), or if it gives more precise timing. Auras, the first symptom of a focal seizure, are already part of the seizure and give seconds to a minute or two of warning; that is the lead time the device has to beat. The warning-window analysis (Section 14.4) shows how performance changes as the window narrows.

## 3. Infra-slow activity: was it recorded?

Before testing infra-slow features, `scripts/check_infraslow.py` looked at the median power spectrum below 3 Hz of 12 random recordings per dataset (`results/d2_plus/infraslow_check.md`):

| Dataset | Power 0.01–0.1 Hz ÷ 0.5–2 Hz | Slope below 0.5 Hz | Reading |
|---|---|---|---|
| CHB-MIT | 0.004 | +1.53 | Power falls steeply below 0.5 Hz: the amplifiers' high-pass filter removed infra-slow activity. No feature can recover it |
| Siena | 0.77 | −0.46 | Some slow activity recorded, despite the header's "HP 1.59 Hz" (probably a display setting) |
| SeizeIT2 | 7.7 | −1.13 | Strong low-frequency power. In a wearable this includes electrode drift and movement as well as brain activity |

The spectra (`results/d2_plus/infraslow_check.png`) make this plain. CHB-MIT's power falls by almost three orders of magnitude from 0.5 Hz down to 0.01 Hz. Siena's stays flat across the infra-slow range. SeizeIT2's rises to about ten times Siena's, which is more than brain activity alone would give and points to electrode drift and movement in a wearable.

So for most of the development data (CHB-MIT), a longer window can't add infra-slow information; the 10 min context features already give the frozen design a longer look at the 0.5–45 Hz features. The `slow` challenger still runs on both development sets as planned, and SeizeIT2 is where it has a chance.

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

## 6. Seizure detection, seizure by seizure

`scripts/plot_missed_seizures.py` scored each seizure on its own (D1 model, seed 0; `results/d2_plus/missed_seizures.md`): the AUROC of the ictal probability for the windows lying entirely inside it, against the same patient's interictal windows.

| Group | Seizures scored | Median AUROC | AUROC ≥ 0.9 | AUROC < 0.7 |
|---|---|---|---|---|
| All | 108 | 0.965 | 57% | 32% |
| CHB-MIT | 101 | 0.937 | 54% | 35% |
| Siena | 7 | 0.995 | 100% | 0% |
| Shorter than 60 s | 36 | 0.981 | 56% | 31% |
| 60 s or longer | 72 | 0.941 | 58% | 33% |

Most seizures are detected almost perfectly, by a model that has never seen the patient. The pooled 0.865 is pulled down by about a third of seizures that the model misses, and they cluster in a few children (chb13, chb15, chb01, chb08). Several score well below 0.5: the model gives *less* seizure probability during them than during normal EEG, so these seizures look unlike any it learned from other patients, rather than merely faint. Duration doesn't explain it (short and long seizures score alike). Of the test patients' 151 seizures, 43 are shorter than one 30 s window, so no window lies entirely inside them and they aren't in this table. They are part of why D1's pooled detection (0.810 over all ictal windows, 0.865 over windows entirely inside a seizure) is lower than the typical seizure's.

**Can you see the difference?** Yes (`results/d2_plus/missed_seizures.png`, three worst and three best detected seizures, 20 s before to 40 s after onset):

* **Missed (chb13, two seizures):** the seizure is clearly visible by eye. A rhythmic discharge starts about 5 s after onset, but only on the frontal and left temporal channels (Fp1-F7, F7-T7, Fp2-F8), at about twice the background amplitude. The other channels barely change.
* **Missed (chb15):** within the first 40 s there is no obvious change on these 8 channels; the seizure may start elsewhere (central or midline channels) or build up later.
* **Detected (chb09, chb11, chb19):** large, fast, widespread activity on every channel, many times the background amplitude.

So the model detects seizures that change the whole head strongly and misses ones that stay focal and moderate. That fits how the features are built: each feature is summarized across the 18 channels by mean, SD, minimum and maximum, so a change on 3 channels moves the summary much less than a change on all 18. Seen from other patients, a frontal rhythm can also look like eye-movement artifact, which is common in normal EEG; that would explain why these seizures score *below* normal EEG. A personalized model (which learns the patient's own seizures) or per-channel features would be expected to catch them; per-channel features are already on the v3 list.

## 7. PPV, NPV and confusion matrices

From the alarm results already committed (`results/d2_plus/existing_results.md`). PPV is the share of alarms followed by a seizure within 30 min; NPV is the share of warning-free 30 min stretches with no seizure.

| Result | Seizures warned | False alarms / 24 h | PPV | NPV | Seizures per day in the data |
|---|---|---|---|---|---|
| D1, cross-patient | 21% | 10.6 | 0.06 | 0.94 | 2.7 |
| Frozen design, CHB-MIT and Siena | 16% | 3.4 | 0.18 | 0.92 | 4.3 |
| Frozen design, SeizeIT2 development | 46% | 4.6 | 0.28 | 0.95 | 3.6 |
| Frozen design, SeizeIT2 lockbox (20 new patients) | 38% | 5.8 | 0.10 | 0.98 | 1.6 |
| Other patients only, same lockbox patients | 12% | 4.9 | 0.04 | 0.97 | 1.6 |

(All at the ≤ 5 false alarms per 24 h setting, except D1's ≤ 10.)

* **On the lockbox, about 1 alarm in 10 was followed by a seizure.** At home seizure rates it would be lower: about 1 in 16 at one seizure a day, and about 1 in 110 at one a week. That is the clearest way to say the device isn't ready, and why the false-alarm rate matters as much as sensitivity.
* **NPV is high for every model,** including the near-chance ones, because almost every 30 minutes is seizure-free. A device that never alarmed would score about the same, so NPV says little here.
* **D1's window-level confusion matrix** (most likely class, preictal vs interictal): sensitivity 0.30, specificity 0.73, PPV 0.09 with 8.6% of windows preictal. A PPV barely above the share of preictal windows matches D1's near-chance AUROC.

Both depend on how often seizures happen, which is why the evaluation methods (Section 8) don't use them as pass/fail criteria. The new runs add confusion matrices at each alarm threshold and time-based PPV/NPV.

## 8. Why seeds mattered so much in v1

The seed changes how the model is trained (here, which training windows are held back to decide when to stop). With many patients, those changes mostly cancel out in the average: v2's mean AUROC moved by only about ±0.007 between seeds. But a single patient's AUROC rests on a few seizures, since windows from the same seizure are strongly correlated, so it can move by several hundredths between seeds. v1 trained 297 seeds and kept, for each test patient, the run that scored best on that patient's own test data. Keeping the best of 297 noisy draws pushes every patient up at once, which inflated the reported 0.713; a single run scored 0.568.

v2's own results show both sides (`results/d2_plus/existing_results.md`):

| Result | Mean AUROC | Overall: SD across seeds | One patient: mean range across seeds | One patient: largest range | Mean if each patient's best of 5 seeds were kept |
|---|---|---|---|---|---|
| D1 cross-patient (25 patients) | 0.556 | 0.008 | 0.116 | 0.265 | 0.614 |
| Frozen design, development (22 patients) | 0.700 | 0.008 | 0.069 | 0.200 | 0.735 |

So the instructor's intuition is right for the overall mean: with 25 patients it barely moves between seeds. But one patient's AUROC can move by more than 0.25. Keeping each patient's best of just **5** seeds would have raised D1 from 0.556 to 0.614, the same size as D2's entire cross-patient "improvement". With 297 seeds, v1's inflation was larger still.

## 9. Fewer channels scoring higher

| Channels | Mean AUROC (5 seeds) | Higher than all channels in | Wilcoxon p |
|---|---|---|---|
| All 18 | 0.556 | – | – |
| A random half | 0.573 | 14 of 25 patients | 0.059 |
| The 6 Cyton derivations | 0.570 | 16 of 25 patients | 0.20 |

The random half scored higher in all 5 seeds, but the seeds share the same 25 patients, so that isn't five independent results. Per patient, neither difference reaches p < 0.05. Fewer channels don't carry more information. The model is near chance, so small changes in the inputs move it by about this much either way. One plausible mechanism: the features are pooled across channels (mean, SD, minimum and maximum), and pooling over fewer, closer channels can make them less noisy. It shouldn't be read as a reason to use fewer channels.

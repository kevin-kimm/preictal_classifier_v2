# Infra-slow check: was EEG below 0.5 Hz recorded?

Median power spectrum of 30 min from the middle of each sampled recording (all derivations), after the causal 3 Hz low-pass and decimation to 8 Hz used by the slow features.

| Dataset | Recordings | Header prefiltering text (most common) | Power 0.01–0.1 Hz ÷ 0.5–2 Hz | Power 0.1–0.5 Hz ÷ 0.5–2 Hz | Slope below 0.5 Hz (log power per decade) |
|---|---|---|---|---|---|
| CHB-MIT | 12 | (empty) | 0.00357 | 0.175 | +1.53 |
| Siena | 12 | HP:1.591549Hz LP:30Hz N:50Hz | 0.767 | 2.06 | -0.46 |
| SeizeIT2 (development) | 12 | (empty) | 7.67 | 7.98 | -1.13 |

**How to read it.** Ordinary EEG has more power at lower frequencies, so with slow activity recorded the slope below 0.5 Hz is negative (power keeps rising as frequency falls) and the ratios are large. A hardware high-pass makes the slope positive (power falls away below the cut-off) and the ratios small. The slow features are only worth testing where the activity was recorded; the pre-registered `slow` arm is run regardless and interpreted with this check.

Figure: `results/d2_plus/infraslow_check.png`

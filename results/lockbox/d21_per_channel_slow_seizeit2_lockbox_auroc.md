# SeizeIT2 lockbox: D2.1: frozen design + per-channel and infra-slow features, auroc

Generated 2026-10-31T04:14:51 · seeds [0] · 67 patients · docs/evaluation_methods.md v1.28, Section 14.12.

| Design | Patients | Mean AUROC | 95% CI |
|---|---|---|---|
| D2.1: frozen design + per-channel and infra-slow features | 62 | 0.624 | 0.566–0.677 |
| Frozen design (same patients, lockbox run of v1.18) | 62 | 0.621 | 0.564–0.671 |

**Paired:** D2.1 minus frozen +0.003 (95% CI -0.013 to +0.017); D2.1 higher in 35 of 62 patients; Wilcoxon p = 0.148.

**Verdict by the rule fixed in v1.28 (Section 14.12):** NOT CONFIRMED (the 95% interval of the difference includes zero, or the difference isn't positive); the frozen design remains the reported final design.

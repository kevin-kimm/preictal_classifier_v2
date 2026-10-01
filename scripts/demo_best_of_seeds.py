"""Teaching figure: keeping the best of many random seeds makes a model look better than it is.

A simulation, not an analysis of real EEG. v6 (the final version of the original AuraSense
pipeline) trained one run with seed 42 (mean AUC 0.568 over 12 Siena patients), then tried 297
more seeds and kept, for each patient, the model with that patient's highest test AUC (reported
mean 0.713, 8 of 12 patients at or above 0.70). Here each patient's "true" AUC is taken to be
their seed-42 result, and every extra seed only adds random variation of the size v6's README
reports (about +/-0.03 to 0.05). No seed is genuinely better. Keeping the best one anyway
reproduces v6's reported numbers.

Usage, from the repo root with .venv active:
    python scripts/demo_best_of_seeds.py

Output: results/figures/demo_best_of_seeds.png
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[1]
RUN1 = np.array([0.326, 0.603, 0.584, 0.561, 0.653, 0.409, 0.714, 0.654, 0.597, 0.635, 0.454, 0.628])  # v6 seed 42
V6_REPORTED, V6_PREDICTABLE = 0.713, 8
N_SEEDS, SIMS = 297, 4000
INK, MUTED = "#1f2933", "#6b7785"


def main():
    rng = np.random.default_rng(0)
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), gridspec_kw={"width_ratios": [1.1, 1.3, 0.9]})

    # A: one patient, 297 tries
    ax = axes[0]
    tries = rng.normal(0.60, 0.05, N_SEEDS)
    ax.hist(tries, bins=30, color="#90cdf4", edgecolor="white")
    ax.axvline(tries.mean(), color=INK, lw=2)
    ax.axvline(tries.max(), color="#c05621", lw=2.5)
    ax.text(tries.mean() - 0.005, ax.get_ylim()[1] * 0.92, f"typical\n{tries.mean():.2f}", ha="right", fontsize=10)
    ax.text(tries.max() + 0.004, ax.get_ylim()[1] * 0.92, f"best of 297\n{tries.max():.2f}", ha="left",
            fontsize=10, color="#c05621")
    ax.set_title("A. One patient, 297 random seeds,\nnone genuinely better", fontsize=11.5, color=INK)
    ax.set_xlabel("test AUC", fontsize=10, color=MUTED)
    ax.set_yticks([])
    ax.set_xlim(0.42, 0.82)

    # B: the more tries you keep the best of, the better it looks
    ax = axes[1]
    ns = np.unique(np.round(np.logspace(0, np.log10(N_SEEDS), 25)).astype(int))
    for sd, color in ((0.03, "#bee3f8"), (0.04, "#63b3ed"), (0.05, "#2b6cb0")):
        draws = rng.normal(RUN1[None, :, None], sd, size=(SIMS // 4, len(RUN1), N_SEEDS))
        best = [draws[:, :, :n].max(axis=2).mean() for n in ns]
        ax.plot(ns, best, color=color, lw=2.2, label=f"seed-to-seed variation ±{sd:.2f}")
    ax.axhline(RUN1.mean(), color=INK, lw=1.2, ls="--")
    ax.text(1.1, RUN1.mean() - 0.012, f"v6 single run: {RUN1.mean():.3f}", fontsize=9.5, color=INK, va="top")
    ax.axhline(V6_REPORTED, color="#c05621", lw=1.2, ls="--")
    ax.text(1.1, V6_REPORTED + 0.004, f"v6 reported (best of 297): {V6_REPORTED}", fontsize=9.5, color="#c05621")
    ax.set_xscale("log")
    ax.set_xlabel("number of seeds tried (keep the best per patient)", fontsize=10, color=MUTED)
    ax.set_ylabel("mean AUC over 12 patients", fontsize=10, color=MUTED)
    ax.set_title("B. Keeping the best of more tries raises the score,\nwith no real improvement", fontsize=11.5,
                 color=INK)
    ax.legend(fontsize=9, frameon=False, loc="lower right")
    ax.set_ylim(0.54, 0.76)

    # C: patients graded "predictable" (AUC >= 0.70)
    ax = axes[2]
    draws = rng.normal(RUN1[None, :, None], 0.05, size=(SIMS, len(RUN1), N_SEEDS)).max(axis=2)
    luck = (draws >= 0.70).sum(axis=1).mean()
    bars = [("single run\n(seed 42)", (RUN1 >= 0.70).sum(), "#a0aec0"),
            ("best of 297 by luck\n(simulated, ±0.05)", luck, "#63b3ed"),
            ("v6 reported", V6_PREDICTABLE, "#c05621")]
    for i, (label, v, c) in enumerate(bars):
        ax.bar(i, v, color=c, width=0.65)
        ax.text(i, v + 0.2, f"{v:.1f}" if isinstance(v, float) else f"{v}", ha="center", fontsize=11, color=INK)
    ax.set_xticks(range(3))
    ax.set_xticklabels([b[0] for b in bars], fontsize=9)
    ax.set_ylim(0, 12)
    ax.set_ylabel("patients with AUC ≥ 0.70 (of 12)", fontsize=10, color=MUTED)
    ax.set_title("C. Patients graded \"predictable\"", fontsize=11.5, color=INK)

    for ax in axes:
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    fig.suptitle("Picking the best of many tries, judged on the test patients, makes a model look better than it is "
                 "(simulation)", fontsize=13, color=INK)
    fig.tight_layout()
    out = REPO / "results" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "demo_best_of_seeds.png", dpi=170, bbox_inches="tight")
    print(f"Saved {out / 'demo_best_of_seeds.png'}")
    print(f"Simulated best of {N_SEEDS} with ±0.05: patients >= 0.70: {luck:.1f} of 12 (v6 reported {V6_PREDICTABLE})")


if __name__ == "__main__":
    main()

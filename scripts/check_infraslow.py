"""Did the recordings capture infra-slow EEG (below 0.5 Hz) at all? (docs/evaluation_methods.md v1.25,
Section 14.7; the instructor's comment on window length.)

Clinical EEG amplifiers usually apply a hardware high-pass filter (often between 0.016 and 0.5 Hz). Below it,
the signal is mostly gone, and no feature can bring it back. This looks at that before any slow feature is
trusted:

* the "prefiltering" text in the EDF headers (often empty, so it can't be relied on);
* the power spectrum from 0.005 to 3 Hz of 30 min from the middle of up to 12 recordings per dataset
  (random, seed 0), after the same causal decimation as the slow features. A spectrum that keeps rising
  towards low frequencies (roughly 1/f) means slow activity was recorded; one that falls steeply below some
  frequency marks the hardware high-pass.

Usage, from the repo root with .venv active:
    python scripts/check_infraslow.py

Outputs: results/d2_plus/infraslow_check.md and infraslow_check.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.data.edf import read_header  # noqa: E402
from preictal.features.slow import DECIM_FS, decimate_causal  # noqa: E402

N_PER_DATASET = 12
STRETCH_S = 1800.0
SEG_S = 200.0


def prefilter_texts(path: Path) -> list[str]:
    """The 80-character prefiltering field of each signal in an EDF header."""
    raw = path.read_bytes()[:256]
    ns = int(raw[252:256].decode("latin-1").strip())
    head = path.read_bytes()[:256 + ns * 256]
    off = 256 + ns * (16 + 80 + 8 + 8 + 8 + 8 + 8)
    return [head[off + i * 80: off + (i + 1) * 80].decode("latin-1").strip() for i in range(ns)]


def spectrum(x8: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    seg = int(SEG_S * DECIM_FS)
    w = np.hanning(seg)
    freqs = np.fft.rfftfreq(seg, 1 / DECIM_FS)
    ps = []
    for c in range(x8.shape[0]):
        if np.isnan(x8[c]).all():
            continue
        x = x8[c][int(60 * DECIM_FS):]                    # drop the filter warm-up
        for s in range(0, len(x) - seg + 1, seg // 2):
            fr = x[s:s + seg]
            fr = (fr - fr.mean()) * w
            ps.append(np.abs(np.fft.rfft(fr)) ** 2 / (DECIM_FS * (w ** 2).sum()))
    return freqs, (np.median(ps, axis=0) if ps else np.full(len(freqs), np.nan))


def recordings():
    sets = {}
    raw = REPO / "data" / "raw"
    for name, pattern in (("CHB-MIT", "chbmit_*/**/*.edf"), ("Siena", "siena_*/**/*.edf")):
        sets[name] = sorted(raw.glob(pattern))
    split = REPO / "configs" / "seizeit2_split.yaml"
    if split.exists():
        import yaml
        dev = yaml.safe_load(split.read_text())["development"]
        root = raw / "seizeit2_v1.1.0"
        sets["SeizeIT2 (development)"] = sorted(p for s in dev for p in (root / s).glob("ses-*/eeg/*_eeg.edf"))
    return sets


def read_middle(name: str, path: Path):
    hdr = read_header(path)
    mid = hdr.duration_s / 2
    a, b = max(0.0, mid - STRETCH_S / 2 - 60), min(hdr.duration_s, mid + STRETCH_S / 2)
    if name.startswith("SeizeIT2"):
        sys.path.insert(0, str(REPO / "scripts"))
        from extract_slow_features import read_stretch
        x, fs, _ = read_stretch("seizeit2", path, a, b)
    else:
        from preictal.data.harmonize import harmonize
        h = harmonize(hdr, start_s=a, stop_s=b)
        x, fs = h.data, h.fs
    return x, fs


def main():
    out = REPO / "results" / "d2_plus"
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    lines = ["# Infra-slow check: was EEG below 0.5 Hz recorded?", "",
             "Median power spectrum of 30 min from the middle of each sampled recording (all derivations), after "
             "the causal 3 Hz low-pass and decimation to 8 Hz used by the slow features.", "",
             "| Dataset | Recordings | Header prefiltering text (most common) | Power 0.01–0.1 Hz ÷ 0.5–2 Hz "
             "| Power 0.1–0.5 Hz ÷ 0.5–2 Hz | Slope below 0.5 Hz (log power per decade) |",
             "|---|---|---|---|---|---|"]
    curves = {}
    for name, files in recordings().items():
        if not files:
            continue
        pick = [files[i] for i in sorted(rng.choice(len(files), size=min(N_PER_DATASET, len(files)), replace=False))]
        specs, pre = [], []
        for p in pick:
            try:
                pre += [t for t in prefilter_texts(p) if t]
                x, fs = read_middle(name, p)
                if x.shape[1] < (SEG_S + 60) * fs:
                    continue
                f, s = spectrum(decimate_causal(x, fs))
                specs.append(s)
            except Exception as e:          # keep going; one odd file shouldn't stop the check
                print(f"  skipped {p.name}: {e}")
        if not specs:
            continue
        S = np.nanmedian(specs, axis=0)
        curves[name] = (f, S, len(specs))
        band = lambda lo, hi: S[(f >= lo) & (f < hi)].sum()                       # noqa: E731
        ref = band(0.5, 2.0)
        m = (f >= 0.01) & (f <= 0.5)
        slope = np.polyfit(np.log10(f[m]), np.log10(S[m] + 1e-20), 1)[0] if m.sum() > 2 else float("nan")
        common = max(set(pre), key=pre.count) if pre else "(empty)"
        lines.append(f"| {name} | {len(specs)} | {common[:60]} | {band(0.01, 0.1) / ref:.3g} | {band(0.1, 0.5) / ref:.3g} "
                     f"| {slope:+.2f} |")
    lines += ["", "**How to read it.** Ordinary EEG has more power at lower frequencies, so with slow activity "
              "recorded the slope below 0.5 Hz is negative (power keeps rising as frequency falls) and the ratios are "
              "large. A hardware high-pass makes the slope positive (power falls away below the cut-off) and the "
              "ratios small. The slow features are only worth testing where the activity was recorded; the "
              "pre-registered `slow` arm is run regardless and interpreted with this check.", ""]
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 4.2))
        for name, (f, S, n) in curves.items():
            m = (f >= 0.005) & (f <= 3)
            ax.loglog(f[m], S[m], label=f"{name} ({n} recordings)")
        ax.axvspan(0.01, 0.5, color="#f1c40f", alpha=0.15, label="infra-slow range")
        ax.set_xlabel("frequency (Hz)")
        ax.set_ylabel("power (µV²/Hz), median")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(out / "infraslow_check.png", dpi=150)
        lines.append("Figure: `results/d2_plus/infraslow_check.png`")
    except Exception as e:
        lines.append(f"(figure not drawn: {e})")
    (out / "infraslow_check.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

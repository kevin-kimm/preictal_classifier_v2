"""Look at the wearable EEG before and during SeizeIT2 seizures (development patients only).

A visual sanity check, not a test: is the behind-the-ear EEG real EEG, do the annotated onsets line up
with visible changes, and does the model's risk rise beforehand? For each chosen seizure it plots:

    top      20 s snippets of the 3 behind-the-ear channels, with a µV scale bar and each channel's RMS amplitude (top to bottom: BTEleft / BTEright / CROSStop) at 60, 20 and 5 min before onset,
             the 20 s ending 5 s before onset, and 0-20 s into the seizure (0.5-40 Hz)
    middle   a spectrogram of a recorded channel from 60 min before to 2 min after onset (0.5-40 Hz, log power)
    bottom   if saved scores exist, the risk the model gave this seizure when it was held out
             (results/d2_plus/seizeit2/scores/<arm>_<patient>_seed0.npz), over the same hour

Only the 25 SeizeIT2 development patients can be plotted; the script refuses lockbox patients.

Usage, from the repo root with .venv active:
    python scripts/plot_seizeit2_leadup.py                              3 development patients, first usable seizure
    python scripts/plot_seizeit2_leadup.py --subjects sub-034 sub-005 --seizures 2
    python scripts/plot_seizeit2_leadup.py --arm per_channel_slow       risk from a different saved arm

Outputs: results/d2_plus/seizeit2_leadup/<patient>_seizure_<hours into recording>h.png
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np
import yaml
from scipy.signal import butter, sosfiltfilt, spectrogram

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.config import load_config  # noqa: E402
from preictal.data.edf import read_header  # noqa: E402
from preictal.data.labels import LabelRules  # noqa: E402
from preictal.data.seizeit2 import CHANNELS, discover_patient, read_bte, timeline  # noqa: E402

ROOT = REPO / "data" / "raw" / "seizeit2_v1.1.0"
POINTS = [(-3600, "60 min before"), (-1200, "20 min before"), (-300, "5 min before"),
          (-25, "ending 5 s before"), (0, "seizure, 0-20 s")]
SNIPPET_S, LEAD_S, AFTER_S = 20.0, 3600.0, 120.0


def read_stretch(p, t0, t1):
    """Behind-the-ear EEG (3 x n, µV) for timeline times t0..t1 inside placed recording p, and its rate."""
    hdr = read_header(p.rec.path)
    a, b = max(0.0, t0 - p.start), min(p.duration, t1 - p.start)
    r0 = int(math.floor(a / hdr.record_s))
    r1 = min(hdr.n_records, int(math.ceil(b / hdr.record_s)))
    x, present, fs, _ = read_bte(p.rec.path, r0, r1 - r0)
    i0 = int(round((a - r0 * hdr.record_s) * fs))
    return x[:, i0:i0 + int(round((b - a) * fs))], fs, a + p.start


def event_types(path: Path) -> dict[float, str]:
    tsv = path.with_name(path.name[: -len("_eeg.edf")] + "_events.tsv")
    out = {}
    if tsv.exists():
        with open(tsv, newline="") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                if (r.get("eventType") or "").lower().startswith("sz"):
                    out[round(float(r["onset"]), 1)] = " ".join(
                        x for x in (r.get("eventType"), r.get("localization"), r.get("vigilance")) if x and x != "n/a")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subjects", nargs="+", default=None, help="development patients, e.g. sub-034")
    ap.add_argument("--seizures", type=int, default=1, help="seizures per patient (eligible ones; those with saved scores first)")
    ap.add_argument("--arm", default="per_channel_slow", help="saved scores to overlay (seed 0)")
    args = ap.parse_args()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    split = yaml.safe_load((REPO / "configs" / "seizeit2_split.yaml").read_text())
    dev = list(split["development"])
    if args.subjects:
        bad = [s for s in args.subjects if s not in dev]
        if bad:
            sys.exit(f"Only development patients can be plotted (not {', '.join(bad)})")
        subs = args.subjects
    else:
        subs = dev
    rules = LabelRules.from_config(load_config())
    out = REPO / "results" / "d2_plus" / "seizeit2_leadup"
    out.mkdir(parents=True, exist_ok=True)
    sos = butter(4, [0.5, 40], btype="bandpass", fs=256, output="sos")
    made = 0
    for sub in subs:
        if not args.subjects and made >= 3:
            break
        tl = timeline(discover_patient(ROOT, sub), rules)
        sf = REPO / "results" / "d2_plus" / "seizeit2" / "scores" / f"{args.arm}_seizeit2_{sub}_seed0.npz"
        scored = set(np.round(np.load(sf)["onset"], 1)) if sf.exists() else set()
        events = sorted(tl.events, key=lambda e: (round(e.onset, 1) not in scored, e.onset))   # scored ones first
        k = 0
        for ev in events:
            if not ev.eligible or k >= args.seizures:
                continue
            p = next((q for q in tl.placed if q.start <= ev.onset < q.end), None)
            if p is None or ev.onset - rules.preictal_start_s < p.start:
                continue
            k += 1
            kind = event_types(p.rec.path).get(round(ev.onset - p.start, 1), "")
            lo = max(p.start, ev.onset - LEAD_S)
            hi = min(p.end, ev.onset + AFTER_S)
            x, fs, t0 = read_stretch(p, lo, hi)
            if fs != 256:
                from preictal.data.harmonize import resample
                x = np.vstack([resample(np.nan_to_num(c), fs, 256) for c in x])
                fs = 256.0
            x = np.where(np.isnan(x), 0.0, x)
            xf = sosfiltfilt(sos, x, axis=1)
            tt = t0 + np.arange(xf.shape[1]) / fs - ev.onset         # seconds from onset

            fig = plt.figure(figsize=(14, 8.5), dpi=130)
            gs = fig.add_gridspec(3, len(POINTS), height_ratios=[2.2, 1.3, 1.0], hspace=0.45, wspace=0.12)
            snaps = []
            for dt, _ in POINTS:
                m = (tt >= dt) & (tt < dt + SNIPPET_S)
                snaps.append(xf[:, m] if m.sum() > fs * SNIPPET_S * 0.9 else None)
            pre = [s for s in snaps[:-1] if s is not None]
            gap = max(2.5 * np.percentile(np.abs(np.concatenate(pre, axis=1)), 99), 20.0) if pre else 100.0
            for j, ((dt, label), s) in enumerate(zip(POINTS, snaps)):
                ax = fig.add_subplot(gs[0, j])
                if s is None:
                    ax.text(0.5, 0.5, "not recorded", ha="center", va="center", transform=ax.transAxes, color="gray")
                else:
                    ts = np.arange(s.shape[1]) / fs
                    for c in range(s.shape[0]):
                        ax.plot(ts, s[c] - c * gap, color="#c0392b" if j == len(POINTS) - 1 else "black", lw=0.5)
                    if j == len(POINTS) - 1:            # vertical scale bar, just right of the last panel
                        bar = float(10 ** np.floor(np.log10(gap / 2)))
                        bar = next(b * bar for b in (5, 2, 1) if b * bar <= gap * 0.6)
                        y0 = -(len(CHANNELS) - 0.6) * gap
                        tr = ax.get_yaxis_transform()
                        ax.plot([1.05, 1.05], [y0, y0 + bar], color="#2a78d6", lw=2.5, transform=tr, clip_on=False)
                        ax.text(1.09, y0 + bar / 2, f"{bar:g} µV", va="center", fontsize=8, color="#2a78d6",
                                transform=tr, clip_on=False)
                rmsv = [f"{np.sqrt(np.mean(s[c] ** 2)):.0f}" if s is not None and np.std(s[c]) > 0 else "–"
                        for c in range(len(CHANNELS))] if s is not None else []
                if rmsv:
                    label = f"{label}\nRMS µV: " + " / ".join(rmsv)
                ax.set_title(label, fontsize=9)
                ax.set_yticks([-c * gap for c in range(len(CHANNELS))])
                ax.set_yticklabels([c.replace(" SD", "") for c in CHANNELS] if j == 0 else [], fontsize=8)
                ax.set_ylim(-(len(CHANNELS) - 0.4) * gap, 0.7 * gap)
                ax.set_xlabel("s", fontsize=8)
                ax.tick_params(labelsize=7)
            axs = fig.add_subplot(gs[1, :])
            sc = int(np.argmax(np.std(xf, axis=1)))          # a channel that was recorded (absent ones are flat)
            f, ts_, S = spectrogram(xf[sc], fs=fs, nperseg=1024, noverlap=512)
            keep = (f >= 0.5) & (f <= 40)
            axs.pcolormesh(ts_ + tt[0], f[keep], 10 * np.log10(S[keep] + 1e-12), shading="auto", cmap="magma")
            axs.axvline(0, color="white", ls="--", lw=1)
            axs.axvspan(-rules.preictal_start_s, -rules.sph_s, ymin=0.97, ymax=1.0, color="#f1c40f")
            axs.set_ylabel(f"Hz ({CHANNELS[sc].replace(' SD', '')})", fontsize=8)
            axs.set_xlim(-LEAD_S, AFTER_S)
            axs.tick_params(labelsize=7)
            axs.set_title("Spectrogram, 60 min before to 2 min after onset (yellow bar: the 30 min preictal period)",
                          fontsize=9)
            axr = fig.add_subplot(gs[2, :], sharex=axs)
            note = "no saved scores for this seizure and arm"
            if sf.exists():
                z = np.load(sf)
                m = np.isclose(z["onset"], ev.onset) & z["in_pre"]
                if m.any():
                    axr.plot(z["t"][m] - ev.onset, z["score"][m], color="#2a78d6", lw=1)
                    note = f"risk from `{args.arm}` when this seizure was held out (seed 0)"
                    if "in_test" in z.files:
                        inter = z["in_test"] & (z["label"] == 2) & (z["fold"] == z["fold"][m][0])
                        if inter.any():
                            axr.axhline(np.median(z["score"][inter]), color="gray", ls=":", lw=1)
                            note += "; dotted: median risk on this fold's normal EEG"
            axr.axvline(0, color="#c0392b", ls="--", lw=1)
            axr.set_ylim(0, 1)
            axr.set_ylabel("risk", fontsize=8)
            axr.set_xlabel("seconds from seizure onset", fontsize=8)
            axr.set_title(note, fontsize=8)
            axr.tick_params(labelsize=7)
            fig.suptitle(f"SeizeIT2 {sub}, seizure at {ev.onset / 3600:.1f} h" + (f" ({kind})" if kind else "")
                         + f" · channels {gap:.0f} µV apart", fontsize=11)
            f_out = out / f"{sub}_seizure_{ev.onset / 3600:.1f}h.png"
            fig.savefig(f_out, bbox_inches="tight")
            plt.close(fig)
            print(f"{sub} seizure at {ev.onset / 3600:.1f} h: {f_out}")
            made += 1
    if not made:
        print("No eligible seizure with its preictal period recorded was found for these patients.")


if __name__ == "__main__":
    main()

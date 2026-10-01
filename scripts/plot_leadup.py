"""Plot one seizure's lead-up: EEG at 60, 20 and 5 min before onset, in the last 20 s before the
5 s cut-off (the last moment a warning still counts), and during the seizure.

A teaching figure, not an analysis: it shows how ordinary the EEG before a seizure usually
looks compared with the seizure itself. Uses CHB-MIT or Siena (development data) only,
never SeizeIT2, and doesn't change anything in the frozen design.

The top row shows 20 s of eight temporal-chain derivations at each time point, on the same
microvolt scale (band-passed 0.5-40 Hz for display). Each panel's title gives its typical size:
the root-mean-square amplitude over the eight channels, in µV, computed before any clipping. The bottom panel shows how the power at
each frequency evolves over the whole lead-up, averaged over those derivations, with the
same four time points marked.

Usage, from the repo root with .venv active:
    python scripts/plot_leadup.py                          first suitable CHB-MIT seizure
    python scripts/plot_leadup.py --subject chbmit:chb05   a particular patient
    python scripts/plot_leadup.py --subject siena:PN05 --event 2

Output: results/figures/leadup_<patient>_<event>.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.signal import butter, sosfiltfilt, spectrogram  # noqa: E402

from preictal.config import load_config  # noqa: E402
from preictal.data.edf import read_header  # noqa: E402
from preictal.data.harmonize import DERIVATIONS, harmonize  # noqa: E402
from preictal.data.labels import LabelRules, build_timelines  # noqa: E402
from preictal.data.loaders import discover  # noqa: E402

SHOW = ["Fp1-F7", "F7-T7", "T7-P7", "P7-O1", "Fp2-F8", "F8-T8", "T8-P8", "P8-O2"]
POINTS = [(-60 * 60, "60 min before"), (-20 * 60, "20 min before"), (-5 * 60, "5 min before"),
          (-25, "ending 5 s before"), (15, "during the seizure")]
SNIPPET_S = 20.0
LEADUP_S = 65 * 60


def dt_label(dt):
    """x-axis note for the panel close to onset, so its timing is unambiguous."""
    return f"seconds ({dt:+.0f} to {dt + SNIPPET_S:+.0f} s from onset)" if -120 < dt < 0 else None


def covering(tl, t0, t1):
    """The placed recording that contains [t0, t1] on the timeline, if any."""
    for p in tl.placed:
        if p.start <= t0 and t1 <= p.start + p.duration:
            return p
    return None


def segment(p, t0, t1):
    """Harmonized EEG (18 x n, µV, 256 Hz) for timeline times t0..t1 inside placed recording p."""
    h = harmonize(read_header(p.rec.path), start_s=t0 - p.start, stop_s=t1 - p.start)
    return h.data, h.fs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subject", default=None, help="e.g. chbmit:chb05 or siena:PN05")
    ap.add_argument("--event", type=int, default=1, help="which eligible seizure of that patient (1 = first)")
    ap.add_argument("--data-root", type=Path, default=REPO / "data" / "raw")
    args = ap.parse_args()

    rules = LabelRules.from_config(load_config())
    datasets = ("chbmit", "siena") if args.subject is None else (args.subject.split(":")[0],)
    print("Finding a seizure with 65 min of recorded lead up...")
    timelines = build_timelines(discover(args.data_root, datasets=datasets), rules)

    chosen = None
    for tl in sorted(timelines, key=lambda x: x.subject):
        if args.subject and tl.subject != args.subject:
            continue
        n = 0
        for e in tl.events:
            if not e.eligible:
                continue
            n += 1
            ok = all(covering(tl, e.onset + dt, e.onset + dt + SNIPPET_S) for dt, _ in POINTS)
            if ok and (args.subject is None or n == args.event):
                chosen = (tl, e, n)
                break
        if chosen:
            break
    if chosen is None:
        sys.exit("No eligible seizure with all four time points recorded; try another --subject or --event.")
    tl, ev, n = chosen
    print(f"{tl.subject}, seizure {n}: onset {ev.onset / 3600:.2f} h into the timeline")

    idx = [DERIVATIONS.index(d) for d in SHOW]
    sos = butter(4, [0.5, 40], btype="bandpass", fs=256, output="sos")
    snippets = []
    for dt, label in POINTS:
        p = covering(tl, ev.onset + dt, ev.onset + dt + SNIPPET_S)
        x, fs = segment(p, ev.onset + dt - 5, ev.onset + dt + SNIPPET_S + 5)      # 5 s padding for the filter
        x = sosfiltfilt(sos, np.nan_to_num(x[idx]), axis=1)[:, int(5 * fs):int((5 + SNIPPET_S) * fs)]
        snippets.append((label, x, fs))
    spread = np.percentile(np.abs(np.concatenate([s[1] for s in snippets[:-1]], axis=1)), 99.9)
    gap = max(2.2 * spread, 50.0)          # spacing set by the pre-seizure snippets

    # lead-up spectrogram, piece by piece where recordings cover it
    spec_t, spec_f, spec = [], None, []
    t = ev.onset - LEADUP_S
    while t < ev.onset + 120:
        p = covering(tl, t, t + 60)
        if p is not None:
            x, fs = segment(p, t, t + 60)
            x = np.nan_to_num(x[idx])
            f, _, S = spectrogram(x, fs=fs, nperseg=512, noverlap=0, axis=1)
            keep = (f >= 0.5) & (f <= 40)
            spec_f = f[keep]
            spec.append(np.log10(S[:, keep, :].mean(axis=(0, 2)) + 1e-12))
        else:
            spec.append(None)
        spec_t.append((t - ev.onset) / 60)
        t += 60

    n_pan = len(POINTS)
    fig = plt.figure(figsize=(3.7 * n_pan + 0.5, 9.5))
    gs = fig.add_gridspec(2, n_pan, height_ratios=[2.2, 1], hspace=0.35, wspace=0.08)
    for k, (label, x, fs) in enumerate(snippets):
        dt = POINTS[k][0]
        ax = fig.add_subplot(gs[0, k])
        tt = np.arange(x.shape[1]) / fs
        for c in range(x.shape[0]):
            trace = np.clip(x[c], -0.48 * gap, 0.48 * gap)      # keep each channel in its own lane
            ax.plot(tt, trace - c * gap, color="#c53030" if k == n_pan - 1 else "#1f2933", lw=0.6)
        clipped = (np.abs(x) > 0.48 * gap).mean() > 0.005
        rms = float(np.sqrt(np.mean(x ** 2)))           # typical size, before any clipping
        ax.set_title(label + (" (clipped)" if clipped else "") + f"\ntypical size {rms:.0f} µV", fontsize=13,
                     color="#c53030" if k == n_pan - 1 else "#1f2933")
        ax.set_xlim(0, SNIPPET_S)
        ax.set_ylim(-(len(SHOW) - 0.5) * gap, gap * 0.6)
        ax.set_xlabel("seconds" if dt_label(POINTS[k][0]) is None else dt_label(POINTS[k][0]), fontsize=9)
        ax.set_yticks([-c * gap for c in range(len(SHOW))])
        ax.set_yticklabels(SHOW if k == 0 else [], fontsize=8.5)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        if k == 0:
            ax.set_ylabel(f"channels {gap:.0f} µV apart", fontsize=9)

    ax = fig.add_subplot(gs[1, :])
    img = np.full((len(spec_f), len(spec_t)), np.nan)
    for j, s in enumerate(spec):
        if s is not None:
            img[:, j] = s
    ax.imshow(img, aspect="auto", origin="lower", cmap="magma",
              extent=[spec_t[0], spec_t[-1] + 1, spec_f[0], spec_f[-1]])
    for dt, label in POINTS:
        ax.axvline(dt / 60, color="white" if dt < 0 else "#63b3ed", lw=1.2, ls="--")
    ax.axvspan(-30, 0, ymin=0.95, ymax=1.0, color="#f6ad55")
    ax.text(-15, spec_f[-1] * 0.9, "30-minute warning window", ha="center", fontsize=9, color="#1f2933",
            bbox=dict(facecolor="#f6ad55", edgecolor="none", pad=2))
    ax.set_xlabel("minutes relative to seizure onset", fontsize=10)
    ax.set_ylabel("frequency (Hz)", fontsize=10)
    ax.set_title("Power at each frequency over the lead up (brighter = more power, blank = not recorded)",
                 fontsize=11)
    fig.suptitle(f"{tl.subject}, seizure {n}: the EEG before and during a seizure "
                 "(same µV scale in every panel)", fontsize=14)

    out = REPO / "results" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"leadup_{tl.subject.replace(':', '_')}_{n}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    print(f"Saved {path}")


if __name__ == "__main__":
    main()

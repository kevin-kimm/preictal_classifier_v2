"""A PDF with one sample from each dataset: how it came, how it was labeled, and how it looks cleaned.

For each dataset, one recording containing a seizure (if the dataset has any):
  page 1  raw, as stored: header details (date, time, channels, sampling rates, units), the
          seizure annotations exactly as written in the dataset's own files, and 10 s of the
          raw channels around the seizure onset
  page 2  the labels this project gave every 30 s window of that recording (preictal, ictal,
          interictal, excluded) over time, and the same 10 s after cleaning: the common
          18-derivation bipolar montage (SeizeIT2: its behind-the-ear channels) at 256 Hz in µV

Reads a few minutes of EEG per dataset, so it's quick and safe to run alongside other jobs.
SeizeIT2 samples come from development patients only.

Usage, from the repo root with .venv active:
    python scripts/dataset_samples_pdf.py
    python scripts/dataset_samples_pdf.py --datasets chbmit siena

Output: results/figures/dataset_samples.pdf
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from preictal.config import load_config  # noqa: E402
from preictal.data.edf import read_header, read_signals  # noqa: E402
from preictal.data.harmonize import TARGET_FS, harmonize, looks_like_eeg, microvolt_factor, resample  # noqa: E402
from preictal.data.labels import EXCLUDED, ICTAL, INTERICTAL, PREICTAL, LabelRules, build_timelines, window_labels  # noqa: E402
from preictal.data.loaders import discover  # noqa: E402

NAMES = {"chbmit": "CHB-MIT", "siena": "Siena", "tusz": "TUSZ", "tuar": "TUAR", "mental_arith": "Mental arithmetic",
         "seizeit2": "SeizeIT2 (development patients)"}
COLORS = {PREICTAL: "#f6ad55", ICTAL: "#e53e3e", INTERICTAL: "#68d391", EXCLUDED: "#e2e8f0"}
LABEL_TEXT = {PREICTAL: "preictal (30 min to 5 s before)", ICTAL: "ictal (during)",
              INTERICTAL: "interictal (≥ 4 h from any seizure)", EXCLUDED: "excluded (in between)"}
SHOW_S = 10.0


def annotation_text(ds: str, path: Path) -> tuple[str, list[str]]:
    """The dataset's own seizure annotation for this file, as written."""
    try:
        if ds == "chbmit":
            f = next(path.parent.glob("*-summary.txt"))
            lines = f.read_text(errors="replace").splitlines()
            i = next(k for k, l in enumerate(lines) if path.name in l)
            block = []
            for l in lines[i:]:
                if not l.strip() and block:
                    break
                block.append(l)
            return f.name, block[:12]
        if ds == "siena":
            f = next(path.parent.glob("Seizures-list-*.txt"))
            lines = f.read_text(errors="replace").splitlines()
            hits = [k for k, l in enumerate(lines) if path.stem in l]
            k = hits[0] if hits else 0
            return f.name, [l for l in lines[max(0, k - 1):k + 7] if l.strip()][:10]
        if ds in ("tusz", "tuar"):
            f = path.with_suffix(".csv_bi") if ds == "tusz" else path.with_name(path.stem + "_seiz.csv")
            rows = [l for l in f.read_text(errors="replace").splitlines() if l.strip()]
            return f.name, rows[:12]
        if ds == "seizeit2":
            f = path.with_name(path.name[: -len("_eeg.edf")] + "_events.tsv")
            return f.name, [l for l in f.read_text(errors="replace").splitlines() if l.strip()][:8]
    except (StopIteration, OSError):
        pass
    return "(none)", ["This dataset has no seizure annotation file for this recording."]


def raw_segment(path: Path, t0: float, channels=None, max_ch: int = 8):
    """10 s of raw channels as stored (converted to µV for plotting), with their labels and rates."""
    hdr = read_header(path)
    if channels is None:
        idx = [i for i, l in enumerate(hdr.labels) if looks_like_eeg(l)]
        if len(idx) < 4:                                   # bipolar labels such as "FP1-F7"
            skip = ("ECG", "EKG", "EMG", "EOG", "RESP", "SPO2", "PULSE", "MOV", "PHOTIC", "ANNOT", "VNS", "LOC", "ROC")
            idx = [i for i, l in enumerate(hdr.labels) if l.strip() not in ("", "-", ".")
                   and not any(s in l.upper() for s in skip)]
        idx = idx[:max_ch]
    else:
        idx = channels
    idx = [i for i in idx if i is not None]
    r0 = int(np.floor(t0 / hdr.record_s))
    n_rec = int(np.ceil(SHOW_S / hdr.record_s)) + 1
    sig = read_signals(hdr, idx, r0, min(n_rec, hdr.n_records - r0))
    out = []
    for i, x in zip(idx, sig):
        fs = hdr.fs(i)
        a = int(round((t0 - r0 * hdr.record_s) * fs))
        seg = x[a:a + int(SHOW_S * fs)]
        f = microvolt_factor(hdr.units[i])
        out.append((hdr.labels[i], fs, hdr.units[i], seg * (f if f else 1.0)))
    return hdr, out


def plot_traces(ax, traces, fs_list, labels, color="#1f2933", title=""):
    """Stacked traces with a common spacing."""
    spread = np.nanpercentile(np.abs(np.concatenate([t for t in traces if len(t)])), 98) if traces else 1
    gap = max(2.5 * spread, 1e-6)
    for k, (x, fs) in enumerate(zip(traces, fs_list)):
        tt = np.arange(len(x)) / fs
        ax.plot(tt, np.clip(x, -0.5 * gap, 0.5 * gap) - k * gap, color=color, lw=0.6)
    ax.set_yticks([-k * gap for k in range(len(traces))])
    ax.set_yticklabels(labels, fontsize=7.5)
    ax.set_xlim(0, SHOW_S)
    ax.set_xlabel("seconds", fontsize=8.5)
    ax.set_title(f"{title} (channels {gap:.0f} µV apart)", fontsize=10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def text_page(fig, rect, lines, size=8.2):
    ax = fig.add_axes(rect)
    ax.axis("off")
    ax.text(0, 1, "\n".join(lines), va="top", ha="left", family="monospace", fontsize=size)


def sample_standard(ds, rules, L, S):
    recs = discover(REPO / "data" / "raw", datasets=(ds,))
    tls = build_timelines(recs, rules)
    best = None
    for tl in sorted(tls, key=lambda x: x.subject):
        for p in tl.placed:
            if p.rec.seizures:
                eligible = any(e.eligible and p.start <= e.onset < p.start + p.duration for e in tl.events)
                if best is None or (eligible and not best[3]):
                    best = (tl, p, p.rec.seizures[0][0], eligible)
                if eligible:
                    break
        if best and best[3]:
            break
    if best is None:                                   # no seizures in this dataset
        tl = sorted(tls, key=lambda x: x.subject)[0]
        best = (tl, tl.placed[0], None, False)
    tl, p, onset, eligible = best
    starts, labels = window_labels(p, tl, rules, L, S)
    return tl.subject, p, onset, eligible, starts, labels


def sample_seizeit2(rules, L, S):
    import yaml
    from preictal.data.seizeit2 import CHANNELS, discover_patient, read_bte, timeline
    from preictal.data.seizeit2 import window_labels as sz_labels
    split = yaml.safe_load((REPO / "configs" / "seizeit2_split.yaml").read_text())
    root = REPO / "data" / "raw" / "seizeit2_v1.1.0"
    for sub in split["development"]:
        tl = timeline(discover_patient(root, sub), rules)
        for p in tl.placed:
            if p.rec.seizures and any(e.eligible and p.start <= e.onset < p.start + p.duration for e in tl.events):
                starts, labels = sz_labels(p, tl, rules, L, S)
                return tl.subject, p, p.rec.seizures[0][0], True, starts, labels, CHANNELS, read_bte
    raise SystemExit("No SeizeIT2 development patient with an eligible seizure found")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datasets", nargs="+", default=list(NAMES))
    args = ap.parse_args()
    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    L, S = cfg["windows"]["length_s"], cfg["windows"]["step_s"]
    out = REPO / "results" / "figures" / "dataset_samples.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)

    with PdfPages(out) as pdf:
        for ds in args.datasets:
            print(f"{NAMES.get(ds, ds)}...")
            try:
                if ds == "seizeit2":
                    subject, p, onset, eligible, starts, labels, CH, read_bte = sample_seizeit2(rules, L, S)
                else:
                    subject, p, onset, eligible, starts, labels = sample_standard(ds, rules, L, S)
            except Exception as exc:                     # a dataset that isn't downloaded, for example
                print(f"  skipped: {exc}")
                continue
            path = p.rec.path
            t0 = max(0.0, (onset - SHOW_S / 2) if onset is not None else 60.0)
            hdr, raw = raw_segment(path, t0, None if ds != "seizeit2" else
                                   [read_header(path).labels.index(c) if c in read_header(path).labels else None
                                    for c in CH])
            ann_file, ann_lines = annotation_text(ds, path)
            rates = sorted({f"{hdr.fs(i):g}" for i in range(hdr.n_signals)})
            units = sorted({u.strip() or "(blank)" for u in hdr.units})

            # page 1: raw
            fig = plt.figure(figsize=(11, 8.5))
            fig.suptitle(f"{NAMES[ds]}: raw, as stored", fontsize=15, x=0.06, ha="left")
            info = [f"Patient {subject}   file {p.rec.rel_path}",
                    f"Recording start (header): {hdr.start_date} {hdr.start_time}    duration {hdr.duration_s / 3600:.2f} h",
                    f"{hdr.n_signals} signals; sampling rates (Hz): {', '.join(rates)}; units: {', '.join(units)}",
                    "Channel labels: " + ", ".join(hdr.labels[:40]) + (" ..." if hdr.n_signals > 40 else "")]
            info = sum((textwrap.wrap(l, 118) for l in info), [])
            info += ["", f"Seizure annotation, as written in {ann_file}:"] + ["  " + l.replace("\t", "   ")[:115] for l in ann_lines]
            text_page(fig, [0.06, 0.48, 0.9, 0.44], info)
            ax = fig.add_axes([0.12, 0.07, 0.83, 0.38])
            plot_traces(ax, [r[3] for r in raw], [r[1] for r in raw], [f"{r[0]} ({r[1]:g} Hz)" for r in raw],
                        title=f"{SHOW_S:.0f} s of raw channels from {t0:.0f} s"
                              + (f" (seizure onset at {SHOW_S / 2:.0f} s)" if onset is not None else ""))
            if onset is not None:
                ax.axvline(onset - t0, color="#e53e3e", lw=1, ls="--")
            pdf.savefig(fig)
            plt.close(fig)

            # page 2: labels and cleaned signal
            fig = plt.figure(figsize=(11, 8.5))
            fig.suptitle(f"{NAMES[ds]}: labels and cleaned signal", fontsize=15, x=0.06, ha="left")
            ax = fig.add_axes([0.08, 0.72, 0.88, 0.12])
            for c in (EXCLUDED, INTERICTAL, PREICTAL, ICTAL):
                m = labels == c
                if m.any():
                    ax.bar((starts[m] + L) / 60, 1, width=S / 60, color=COLORS[c], align="edge", linewidth=0)
            ax.set_yticks([])
            ax.set_xlim(0, p.duration / 60)
            ax.set_xlabel("minutes into this recording (each bar is the end of one 30 s window, every 5 s)", fontsize=8.5)
            hours = {c: (labels == c).sum() * S / 3600 for c in COLORS}
            ax.legend(handles=[Patch(color=COLORS[c], label=f"{LABEL_TEXT[c]}: {hours[c]:.2f} h") for c in
                               (PREICTAL, ICTAL, INTERICTAL, EXCLUDED)], fontsize=8, ncol=2, frameon=False,
                      loc="lower left", bbox_to_anchor=(0, 1.02))
            for s in ("top", "right", "left"):
                ax.spines[s].set_visible(False)
            note = (f"Seizure in this file is {'eligible' if eligible else 'not eligible'} for prediction "
                    "(at least 90% of its 30 min lead-up recorded)." if onset is not None
                    else "No seizures in this recording: every window is normal EEG (or excluded).")
            fig.text(0.08, 0.66, note, fontsize=9)

            ax = fig.add_axes([0.12, 0.07, 0.83, 0.52])
            if ds == "seizeit2":
                hz = read_header(path)
                r0 = int(np.floor(t0 / hz.record_s))
                bte, present, fs_in, _ = read_bte(path, r0, int(np.ceil(SHOW_S / hz.record_s)) + 1)
                a = int(round((t0 - r0 * hz.record_s) * fs_in))
                traces = [resample(bte[j][a:a + int(SHOW_S * fs_in)], fs_in, TARGET_FS)
                          for j in range(len(CH)) if present[j]]
                names = [c for j, c in enumerate(CH) if present[j]]
                how = "behind-the-ear channels, resampled to 256 Hz, in µV"
            else:
                h = harmonize(read_header(path), start_s=t0, stop_s=t0 + SHOW_S)
                keep = [k for k in range(len(h.derivations)) if h.present[k]]
                traces = [h.data[k] for k in keep]
                names = [h.derivations[k] for k in keep]
                how = f"{len(keep)} of 18 standard bipolar derivations, 256 Hz, µV"
            plot_traces(ax, traces, [TARGET_FS] * len(traces), names, color="#2b6cb0",
                        title=f"The same {SHOW_S:.0f} s, cleaned: {how}")
            if onset is not None:
                ax.axvline(onset - t0, color="#e53e3e", lw=1, ls="--")
            pdf.savefig(fig)
            plt.close(fig)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()

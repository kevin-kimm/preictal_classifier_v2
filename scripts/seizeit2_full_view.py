"""Everything about one SeizeIT2 seizure on one page, in microvolts (development patients only).

Puts the raw behind-the-ear EEG and what the model makes of it side by side, so you can see what the model is
reacting to. The model is rebuilt exactly as it was when this seizure was held out (scripts/explain_seizeit2.py,
checked against the saved scores), by default the final (frozen) design.

    1  snapshots   20 s of each channel (0.5-40 Hz) at 60, 20 and 5 min before onset, just before it and in
                   the first 20 s of the seizure. Each channel has its own µV axis (the four pre-seizure
                   snapshots share one, so they compare directly; the seizure has its own) and its RMS in µV.
    2  bands       for each snapshot, the amplitude in each frequency band the model's features use
                   (delta 0.5-4, theta 4-8, alpha 8-13, beta 13-30, gamma 30-45 Hz), in µV RMS per channel
    3  spectrogram per recorded channel, for the hour before onset and 2 min after, color = power in
                   dB re 1 µV²/Hz (one color scale for all channels)
    4  amplitude   each channel's RMS (µV) per 30 s window, the window the model sees, with that channel's
                   median on this person's normal EEG (dashed) and 5x it (dotted: the audit's artifact level);
                   grey bands = windows the audit flags as artifact
    5  band µV     per recorded channel, the µV RMS in each band over the hour (1 min average)
    6  model       the preictal risk (raw and the 3 min average alarms use), the "seizure happening now"
                   probability, and the median risk on this fold's normal EEG
    7  drivers     which feature groups push the risk up (red) or down (blue): the drop in risk when a group is
                   reset to this person's normal (3 min average)

Dotted vertical lines mark the snapshot times on every time row.

Usage, from the repo root with .venv active:
    python scripts/seizeit2_full_view.py --subject sub-034                   final design, first scored seizure
    python scripts/seizeit2_full_view.py --subject sub-065 --seizure 2
    python scripts/seizeit2_full_view.py --subject sub-034 --arm per_channel_slow

Outputs (results/d2_plus/seizeit2_full/):
    <patient>_seizure_<h>h_<arm>.png
    <patient>_seizure_<h>h_<arm>_windows.csv     per 30 s window: risk, seizure-now probability, drivers, µV
    <patient>_seizure_<h>h_<arm>_snapshots.csv   per snapshot and channel: RMS and band µV
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt, spectrogram, welch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from explain_seizeit2 import ARMS, BANDS, explain  # noqa: E402
from plot_seizeit2_leadup import POINTS, ROOT, SNIPPET_S, event_types, read_stretch  # noqa: E402
from preictal.alarm.alarm import smooth  # noqa: E402
from preictal.data.seizeit2 import CHANNELS, discover_patient, timeline  # noqa: E402
from preictal.evaluation.audit import FLAT_X, HIGH_X  # noqa: E402
from preictal.features.build_features import BANDS as BAND_EDGES, FEATURES_V2  # noqa: E402

LEAD_S, AFTER_S, FS = 3600.0, 120.0, 256.0
CH_COLORS = ["#2a78d6", "#e8833a", "#1b9e77"]
BAND_COLORS = {"delta": "#6250d6", "theta": "#2a78d6", "alpha": "#1baf7a", "beta": "#eda100", "gamma": "#e87ba4"}


def band_uv(x, fs):
    """µV RMS in each feature band for one channel's snippet (Welch, 2 s segments)."""
    f, p = welch(x - np.mean(x), fs=fs, nperseg=int(2 * fs))
    out = {}
    for b in BANDS:
        lo, hi = BAND_EDGES[b]
        m = (f >= lo) & (f < hi)
        out[b] = float(np.sqrt(np.trapezoid(p[m], f[m]))) if m.sum() > 1 else float("nan")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subject", required=True, help="a development patient, e.g. sub-034")
    ap.add_argument("--seizure", type=int, default=1, help="which of its scored seizures (in time order)")
    ap.add_argument("--arm", choices=ARMS, default="frozen", help="frozen (final design) or per_channel_slow (D2.1)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, LogLocator
    plain = FuncFormatter(lambda v, _: f"{v:g}")

    R = explain(args.subject, args.seizure, args.seed, args.arm, LEAD_S, AFTER_S)
    rules, onset, rel_t = R["rules"], R["onset"], R["rel_t"]
    short = R["short"]

    # ---------------------------------------------------------------- raw EEG for the hour
    tlo = timeline(discover_patient(ROOT, short), rules)
    pl = next((q for q in tlo.placed if q.start <= onset < q.end), None)
    if pl is None:
        sys.exit("could not place this seizure in its recording")
    x, fs, t0 = read_stretch(pl, max(pl.start, onset - LEAD_S), min(pl.end, onset + AFTER_S))
    if fs != FS:
        from preictal.data.harmonize import resample
        x = np.vstack([resample(np.nan_to_num(c), fs, FS) if np.isfinite(c).any() else np.full(
            int(round(len(c) * FS / fs)), np.nan) for c in x])
        fs = FS
    present = [c for c in range(x.shape[0]) if np.isfinite(x[c]).any() and np.nanstd(x[c]) > 0]
    xr = np.where(np.isnan(x), 0.0, x)
    xf = sosfiltfilt(butter(4, [0.5, min(40.0, 0.45 * fs)], btype="bandpass", fs=fs, output="sos"), xr, axis=1)
    tt = t0 + np.arange(x.shape[1]) / fs - onset
    kind = event_types(pl.rec.path).get(round(onset - pl.start, 1), "")

    # ---------------------------------------------------------------- snapshots
    snaps = []
    for dt, label in POINTS:
        m = (tt >= dt) & (tt < dt + SNIPPET_S)
        snaps.append((dt, label, m if m.sum() > fs * SNIPPET_S * 0.9 else None))
    snap_rows = []
    lim = {}
    for c in present:
        pre = [np.abs(xf[c, m]) for _, _, m in snaps[:-1] if m is not None]
        lim[c] = 1.15 * float(np.percentile(np.concatenate(pre), 99.5)) if pre else 50.0
    band_vals = {}
    for k, (dt, label, m) in enumerate(snaps):
        for c in present:
            if m is None:
                continue
            seg_raw = xr[c, m]
            bv = band_uv(seg_raw, fs)
            band_vals[(k, c)] = bv
            snap_rows.append({"snapshot": label, "channel": CHANNELS[c].replace(" SD", ""),
                              "rms_uV_0.5_40Hz": round(float(np.sqrt(np.mean(xf[c, m] ** 2))), 2),
                              **{f"{b}_uV": round(v, 2) for b, v in bv.items()}})

    # ---------------------------------------------------------------- per-window µV from the model's own features
    pc = R["pc"]
    F = {f: k for k, f in enumerate(FEATURES_V2)}
    rms_w = np.sqrt(10 ** pc[:, :, F["log_variance"]].astype(float))
    amp_w = {b: np.sqrt(10 ** pc[:, :, F[f"logpow_{b}"]].astype(float)) for b in BANDS}
    nr = R["normal_rms"]
    with np.errstate(invalid="ignore"):
        ratio = rms_w / nr
        flag = (np.nan_to_num(ratio, nan=0).max(axis=1) > HIGH_X) | (np.nan_to_num(ratio, nan=np.inf).min(axis=1) < FLAT_X)

    # ---------------------------------------------------------------- figure
    nP = max(len(present), 1)
    names, C = R["names"], R["C"]
    heights = [1.15] * 3 + [1.7] + [1.15] * nP + [1.5] + [1.1] * nP + [1.5] + [0.35 + 0.22 * len(names)]
    fig = plt.figure(figsize=(18, sum(heights) * 1.25 + 1.5), dpi=120)
    outer = fig.add_gridspec(len(heights), 1, height_ratios=heights, hspace=0.62, top=0.965, bottom=0.03)
    top = outer[0:3].subgridspec(3, len(POINTS), hspace=0.25, wspace=0.18)
    for k, (dt, label, m) in enumerate(snaps):
        for c in range(3):
            ax = fig.add_subplot(top[c, k])
            if m is None or c not in present:
                ax.text(0.5, 0.5, "not recorded", ha="center", va="center", transform=ax.transAxes, color="gray",
                        fontsize=9)
                ax.set_xticks([])
                ax.set_yticks([])
            else:
                seg = xf[c, m]
                ts = np.arange(len(seg)) / fs
                seizure_col = k == len(POINTS) - 1
                ax.plot(ts, seg, color="#c0392b" if seizure_col else "black", lw=0.5)
                L = 1.15 * float(np.percentile(np.abs(seg), 99.5)) if seizure_col else lim[c]
                ax.set_ylim(-L, L)
                ax.set_xlim(0, SNIPPET_S)
                ax.tick_params(labelsize=7)
                ax.text(0.01, 0.97, f"RMS {np.sqrt(np.mean(seg ** 2)):.0f} µV", transform=ax.transAxes, fontsize=8,
                        va="top", color="#1f2a33", bbox=dict(fc="white", ec="none", alpha=0.75, pad=1))
                if c < 2:
                    ax.set_xticklabels([])
                else:
                    ax.set_xlabel("s", fontsize=8)
            if k == 0 or k == len(POINTS) - 1:
                ax.set_ylabel(f"{CHANNELS[c].replace(' SD', '')}\nµV", fontsize=8)
            if c == 0:
                ax.set_title(label + (" (own µV scale)" if k == len(POINTS) - 1 else ""), fontsize=9)

    bars = outer[3].subgridspec(1, len(POINTS), wspace=0.18)
    vmax = max([v for d in band_vals.values() for v in d.values() if np.isfinite(v)] or [1])
    vmin = min([v for d in band_vals.values() for v in d.values() if np.isfinite(v) and v > 0] or [0.1])
    width = 0.8 / nP
    for k in range(len(POINTS)):
        ax = fig.add_subplot(bars[0, k])
        for j, c in enumerate(present):
            if (k, c) not in band_vals:
                continue
            vals = [band_vals[(k, c)][b] for b in BANDS]
            ax.bar(np.arange(len(BANDS)) + (j - (nP - 1) / 2) * width, vals, width * 0.92, color=CH_COLORS[c],
                   label=CHANNELS[c].replace(" SD", "") if k == 0 else None)
        ax.set_yscale("log")
        ax.set_ylim(vmin * 0.7, vmax * 1.5)
        ax.yaxis.set_major_locator(LogLocator(subs=(1.0, 2.0, 5.0)))
        ax.yaxis.set_major_formatter(plain)
        ax.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))
        ax.set_xticks(range(len(BANDS)))
        ax.set_xticklabels(["δ", "θ", "α", "β", "γ"], fontsize=9)
        ax.tick_params(labelsize=7)
        if k == 0:
            ax.set_ylabel("µV RMS\nper band", fontsize=8)
            ax.legend(fontsize=7, frameon=False, loc="upper right")
        ax.set_title("bands: δ 0.5–4, θ 4–8, α 8–13, β 13–30, γ 30–45 Hz" if k == 0 else "", fontsize=8, loc="left")

    # time rows
    row = 4
    t_axes = []
    first = None
    spec_db = []
    for c in present:
        f, ts_, S = spectrogram(xf[c], fs=fs, nperseg=1024, noverlap=512)
        keep = (f >= 0.5) & (f <= 40)
        spec_db.append((c, f[keep], ts_ + tt[0], 10 * np.log10(S[keep] + 1e-12)))
    allv = np.concatenate([d.ravel() for *_, d in spec_db]) if spec_db else np.array([0, 1])
    v0, v1 = np.percentile(allv, 5), np.percentile(allv, 99.5)
    for c, fq, tsx, D in spec_db:
        ax = fig.add_subplot(outer[row], sharex=first) if first else fig.add_subplot(outer[row])
        first = first or ax
        mesh = ax.pcolormesh(tsx, fq, D, shading="auto", cmap="magma", vmin=v0, vmax=v1)
        ax.set_ylabel(f"{CHANNELS[c].replace(' SD', '')}\nHz", fontsize=8)
        ax.set_title(f"Spectrogram, {CHANNELS[c].replace(' SD', '')}" + (" · color: dB re 1 µV²/Hz" if c == present[0] else ""),
                     fontsize=9, loc="left")
        cax = ax.inset_axes([1.005, 0.0, 0.008, 1.0])
        cb = fig.colorbar(mesh, cax=cax)
        cb.ax.tick_params(labelsize=7)
        t_axes.append(ax)
        row += 1

    ax = fig.add_subplot(outer[row], sharex=first) if first else fig.add_subplot(outer[row])
    first = first or ax
    for c in present:
        ax.plot(rel_t, rms_w[:, c], color=CH_COLORS[c], lw=1, label=f"{CHANNELS[c].replace(' SD', '')}")
        if np.isfinite(nr[c]):
            ax.axhline(nr[c], color=CH_COLORS[c], ls="--", lw=0.8)
            ax.axhline(HIGH_X * nr[c], color=CH_COLORS[c], ls=":", lw=0.8)
    for j in np.flatnonzero(flag):
        ax.axvspan(rel_t[j] - 2.5, rel_t[j] + 2.5, color="#9aa5ad", alpha=0.25, lw=0)
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(LogLocator(subs=(1.0, 2.0, 5.0)))
    ax.yaxis.set_major_formatter(plain)
    ax.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))
    ax.set_ylabel("µV RMS", fontsize=8)
    ax.legend(fontsize=7, frameon=False, loc="upper left", ncol=3)
    ax.set_title("Amplitude of each 30 s window the model sees (µV RMS). Dashed: this person's normal; dotted: 5x normal "
                 "(artifact level); grey: artifact-flagged windows", fontsize=9, loc="left")
    t_axes.append(ax)
    row += 1

    for c in present:
        ax = fig.add_subplot(outer[row], sharex=first)
        for b in BANDS:
            ax.plot(rel_t, smooth(np.nan_to_num(amp_w[b][:, c]), 12), color=BAND_COLORS[b], lw=1, label=b)
        ax.set_yscale("log")
        ax.yaxis.set_major_locator(LogLocator(subs=(1.0, 2.0, 5.0)))
        ax.yaxis.set_major_formatter(plain)
        ax.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))
        ax.set_ylabel("µV RMS", fontsize=8)
        ax.set_title(f"{CHANNELS[c].replace(' SD', '')}: µV in each band (1 min average)", fontsize=9, loc="left")
        if c == present[0]:
            ax.legend(fontsize=7, ncol=5, frameon=False, loc="upper left")
        t_axes.append(ax)
        row += 1

    ax = fig.add_subplot(outer[row], sharex=first)
    ax.plot(rel_t, R["risk"], color="#9cc3ef", lw=0.8, label="preictal risk (raw)")
    ax.plot(rel_t, smooth(R["risk"], 36), color="#2a78d6", lw=1.6, label="preictal risk, 3 min average (alarms use this)")
    ax.plot(rel_t, R["ictal"], color="#e34948", lw=1.2, label="'seizure happening now' probability")
    if np.isfinite(R["normal_risk"]):
        ax.axhline(R["normal_risk"], color="gray", ls=":", lw=1, label="median risk on this fold's normal EEG")
    ax.axvspan(-rules.preictal_start_s, -rules.sph_s, color="#f1c40f", alpha=0.12, label="30 min preictal period")
    ax.set_ylim(0, 1)
    ax.set_ylabel("probability", fontsize=8)
    ax.legend(fontsize=7, loc="upper left", bbox_to_anchor=(1.005, 1.0), frameon=False)
    ax.set_title(f"What the model concluded ({R['arm']} design, seed {R['seed']}, this seizure held out)", fontsize=9, loc="left")
    t_axes.append(ax)
    row += 1

    ax = fig.add_subplot(outer[row], sharex=first)
    climv = max(np.nanmax(np.abs(C)), 0.02)
    ax.pcolormesh(rel_t, np.arange(len(names) + 1), C[:, :-1] if C.shape[1] > 1 else C, cmap="RdBu_r",
                  vmin=-climv, vmax=climv, shading="flat")
    ax.set_yticks(np.arange(len(names)) + 0.5)
    ax.set_yticklabels(names, fontsize=7)
    ax.set_title(f"What pushes the risk up (red) or down (blue): drop in risk when each group is reset to this person's "
                 f"normal (3 min average, scale ±{climv:.2f})", fontsize=9, loc="left")
    ax.set_xlabel("seconds from seizure onset", fontsize=9)
    t_axes.append(ax)

    for ax in t_axes:
        ax.axvline(0, color="black", ls="--", lw=1)
        for dt, _, _ in snaps:
            ax.axvline(dt + SNIPPET_S / 2, color="#5b6670", ls=":", lw=0.8)
        ax.tick_params(labelsize=7)
        ax.set_xlim(-LEAD_S, AFTER_S)
    fig.suptitle(f"SeizeIT2 {short}, seizure at {onset / 3600:.1f} h" + (f" ({kind})" if kind else "")
                 + f" · {R['arm']} model {R['check']}", fontsize=12, y=0.99)

    out = REPO / "results" / "d2_plus" / "seizeit2_full"
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"{short}_seizure_{onset / 3600:.1f}h_{R['arm']}".replace(".", "_")
    fig.savefig(stem.with_suffix(".png"), bbox_inches="tight")
    plt.close(fig)

    with open(f"{stem}_windows.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        chs = [CHANNELS[c].replace(" SD", "") for c in range(rms_w.shape[1])]
        w.writerow(["seconds_from_onset", "risk", "ictal_probability", "artifact_flag"] + names
                   + [f"rms_uV_{ch}" for ch in chs] + [f"{b}_uV_{ch}" for ch in chs for b in BANDS])
        for k in range(len(rel_t)):
            w.writerow([round(rel_t[k], 1), round(float(R["risk"][k]), 5), round(float(R["ictal"][k]), 5), int(flag[k])]
                       + [round(float(C[j, k]), 5) for j in range(len(names))]
                       + [round(float(v), 2) if np.isfinite(v) else "" for v in rms_w[k]]
                       + [round(float(amp_w[b][k, c]), 2) if np.isfinite(amp_w[b][k, c]) else ""
                          for c in range(rms_w.shape[1]) for b in BANDS])
    if snap_rows:
        with open(f"{stem}_snapshots.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(snap_rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(snap_rows)
    print(f"Figure: {stem.with_suffix('.png')}")
    print(f"Tables: {stem}_windows.csv, {stem}_snapshots.csv")


if __name__ == "__main__":
    main()

"""What is the model reacting to before a SeizeIT2 seizure? (development patients only)

For one held-out seizure, this rebuilds the exact model the D2 improvement round used for it (by default the
`per_channel_slow` design; `--arm frozen` for the final design; seed 0: other development patients + this
patient's other seizures and normal EEG) and first checks that it reproduces the saved risk scores. Then, for the hour before onset and 2 min after:

    row 1  the model's two outputs: preictal risk (what alarms use; raw and 3 min average) and the
           probability it gives to "a seizure is happening now" (ictal)
    row 2  which feature groups push the preictal risk up or down: each group in turn is reset to this
           person's normal value (its personal-baseline median) and the drop in risk is recorded
           (3 min average). Red = that group is raising the risk, blue = lowering it. Groups interact, so
           the rows don't add up to the risk; they show what the model leans on, not a full breakdown.
    row 3  the EEG itself, as amplitude in microvolts (RMS) in each frequency band, for each recorded
           channel, from the same 30 s windows the model sees
    row 4  overall signal amplitude (RMS of each 30 s window, µV) per channel

Everything shown lies within 4 h of the held-out seizure, which the model never trained on.

Usage, from the repo root with .venv active:
    python scripts/explain_seizeit2.py --subject sub-034                  first scored seizure
    python scripts/explain_seizeit2.py --subject sub-034 --seizure 2      its second scored seizure

Outputs: results/d2_plus/seizeit2_explain/<patient>_seizure_<hours, e.g. 1_5h>.png and .csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from preictal.alarm.alarm import smooth  # noqa: E402
from preictal.config import load_config  # noqa: E402
from preictal.data.labels import INTERICTAL, PREICTAL, LabelRules  # noqa: E402
from preictal.data.seizeit2 import CHANNELS, FEATURE_CODE, VERSION_TEXT, cohort  # noqa: E402
from preictal.evaluation.patient_specific import patient_folds  # noqa: E402
from preictal.features.build_features import (  # noqa: E402
    CONNECTIVITY_FEATURES, FEATURES_V2, feature_version,
)
from preictal.features.transforms import cache_key, context_features  # noqa: E402
from preictal.models.model import ColumnSubsetModel, build_model, informative_columns, predict_proba  # noqa: E402
from preictal.models.train import TRAIN_CLASSES, blend_weights, load_windows  # noqa: E402
from run_d2_plus import load_slow  # noqa: E402

OTHERS_EVERY, CONTEXT_S, SMOOTH = 6, 600, 36
LEAD_S, AFTER_S = 3600.0, 120.0
BANDS = ("delta", "theta", "alpha", "beta", "gamma")


def scale(M, ref):
    with np.errstate(all="ignore"):
        med = np.nanmedian(ref, axis=0)
        iqr = np.maximum(np.nanpercentile(ref, 75, axis=0) - np.nanpercentile(ref, 25, axis=0), 1e-3)
    return (M - med) / iqr


def column_groups(n_pooled: int, n_conn: int, n_ctx: int, n_slow: int, n_ch: int, n_feat: int) -> dict:
    """Column indices of each feature group, in the run_d2_plus column order (frozen: pooled, connectivity,
    context; per_channel_slow adds infra-slow and each channel's own features)."""
    names = FEATURES_V2
    band_f = [i for i, f in enumerate(names) if f.startswith(("logpow_", "relpow_"))]
    other_f = [i for i in range(len(names)) if i not in band_f]
    pooled = lambda fs: [f * 4 + s for f in fs for s in range(4)]      # noqa: E731 (pool(): 4 stats per feature)
    g = {"Band power, all channels (summary)": pooled(band_f),
         "Signal shape, all channels (summary)": pooled(other_f),
         "Connectivity between channels": list(range(n_pooled, n_pooled + n_conn))}
    c0 = n_pooled + n_conn
    g["10 min trend (context)"] = list(range(c0, c0 + n_ctx))
    s0 = c0 + n_ctx
    if n_slow:
        g["Infra-slow, last 5 min"] = list(range(s0, s0 + n_slow))
    p0 = s0 + n_slow
    for c in range(n_ch):
        g[f"{CHANNELS[c].replace(' SD', '')} on its own"] = list(range(p0 + c * n_feat, p0 + (c + 1) * n_feat))
    return g


ARMS = ("frozen", "per_channel_slow")


def explain(subject_short: str, seizure: int = 1, seed: int = 0, arm: str = "per_channel_slow",
            lead_s: float = LEAD_S, after_s: float = AFTER_S) -> dict:
    """Rebuild the exact fold model of `arm` for one held-out seizure of a development patient, check it against
    the saved scores, and return everything needed to plot what it reacts to (see the keys at the end)."""
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {ARMS}")
    pc_slow = arm == "per_channel_slow"
    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    _, test_subjects, pool = cohort(REPO, "development")
    subject = subject_short if subject_short.startswith("seizeit2:") else f"seizeit2:{subject_short}"
    short = subject.split(":")[-1]
    if subject not in test_subjects:
        sys.exit(f"{short} isn't a SeizeIT2 development patient (only those can be explained)")
    features = REPO / "data" / "processed" / "features_seizeit2"
    version = feature_version(cfg, VERSION_TEXT, FEATURE_CODE)
    tl_info = json.loads((features / "timelines.json").read_text())

    print("Loading the development patients' features...")
    W = load_windows(features, ("seizeit2",), subjects=pool, version=version, keep_per_channel=True)
    raw_pc = W.per_channel.copy()                       # unscaled per-channel features, for the µV rows
    per_ch = W.per_channel.reshape(len(W.y), -1).astype(np.float32)
    W.per_channel = None
    cache = features.parent / "d2_cache" / f"train_ctx10r_{version}_{cache_key(W)}.npy"
    ctx = np.load(cache) if cache.exists() else context_features(W.X, W.timeline, W.t_end, CONTEXT_S)
    if pc_slow:
        slow = load_slow(W, features, ("seizeit2",))
        M_all = np.hstack([W.X, ctx, slow, per_ch]).astype(np.float32)
        groups = column_groups(len(FEATURES_V2) * 4, len(CONNECTIVITY_FEATURES), ctx.shape[1], slow.shape[1],
                               raw_pc.shape[1], raw_pc.shape[2])
    else:
        M_all = np.hstack([W.X, ctx]).astype(np.float32)
        groups = column_groups(len(FEATURES_V2) * 4, len(CONNECTIVITY_FEATURES), ctx.shape[1], 0, 0, 0)
    y = W.y
    code = W.subjects.index(subject)
    every6 = np.round(W.t_end / 5.0).astype(np.int64) % OTHERS_EVERY == 0

    # other patients' training rows, each scaled by their own interictal windows (as in run_d2_plus.py)
    o_rows, o_X = [], []
    for c, s in enumerate(W.subjects):
        if s == subject or s not in pool:
            continue
        r = np.flatnonzero(W.subject == c)
        ref = r[y[r] == INTERICTAL]
        S = (scale(M_all[r], M_all[ref]) if len(ref) else M_all[r]).astype(np.float32)   # stored as float32 there
        keep = np.isin(y[r], TRAIN_CLASSES) & every6[r]
        o_rows.append(r[keep])
        o_X.append(S[keep])
    o = np.concatenate(o_rows)
    Xo = np.vstack(o_X)
    order = np.argsort(o)                       # global row order, as run_d2_plus.py uses
    o, Xo = o[order], Xo[order]
    yo = y[o]

    rows = np.flatnonzero(W.subject == code)
    t, yt, tl = W.t_end[rows], y[rows], W.timeline[rows]
    events = sorted((c, on) for c in np.unique(tl) for on in tl_info[W.timelines[c]]["eligible_onsets"])
    folds = [(i, tr, te) for i, tr, te in patient_folds(t, yt, tl, events, rules.preictal_start_s, rules.sph_s,
                                                         rules.interictal_gap_s, train_labels=yt)
             if (yt[tr] == PREICTAL).any() and (yt[tr] == INTERICTAL).any()]
    if len(folds) < seizure:
        sys.exit(f"{short} has {len(folds)} scored seizures")
    i, train, test = folds[seizure - 1]
    tl_e, onset = events[i]
    M = M_all[rows]
    ref = train[yt[train] == INTERICTAL]
    P = scale(M, M[ref])
    rel = train[np.isin(yt[train], TRAIN_CLASSES)]
    wg, wp = blend_weights(yo, W.subject[o], yt[rel], 0.5)
    X = np.vstack([Xo, P[rel]])
    print(f"Training the {arm} model for {short}'s seizure at {onset / 3600:.1f} h (held out)...")
    base = build_model(seed)
    if pc_slow:                                 # as run_d2_plus.py: drop columns with no information
        keep = informative_columns(X)
        base.fit(X[:, keep], np.concatenate([yo, yt[rel]]), sample_weight=np.concatenate([wg, wp]))
        model = ColumnSubsetModel(base, keep)
    else:
        base.fit(X, np.concatenate([yo, yt[rel]]), sample_weight=np.concatenate([wg, wp]))
        model = base

    show = np.flatnonzero((tl == tl_e) & (t >= onset - lead_s) & (t <= onset + after_s))
    show = show[np.argsort(t[show])]
    prob = predict_proba(model, P[show])
    risk, ictal = prob[:, 0], prob[:, 1]
    rel_t = t[show] - onset
    test_normal = test[yt[test] == INTERICTAL]
    normal_risk = float(np.median(predict_proba(model, P[test_normal])[:, 0])) if len(test_normal) else float("nan")

    # check against the saved scores of the improvement round
    sf = REPO / "results" / "d2_plus" / "seizeit2" / "scores" / f"{arm}_seizeit2_{short}_seed{seed}.npz"
    check = "no saved scores to compare with"
    if sf.exists():
        z = np.load(sf)
        m = np.isclose(z["onset"], onset)
        if m.any():
            lookup = dict(zip(np.round(z["t"][m], 3), z["score"][m]))
            pairs = [(lookup[k], r) for k, r in zip(np.round(t[show], 3), risk) if k in lookup]
            diff = max(abs(a - b) for a, b in pairs) if pairs else float("nan")
            check = (f"reproduces the saved risk exactly ({len(pairs)} windows, largest difference {diff:.1e})"
                     if diff < 1e-5 else f"WARNING: differs from the saved risk by up to {diff:.3f}")
    print("Check:", check)

    # group contributions: risk drop when a group is reset to the person's normal (0 after scaling)
    contrib = {}
    for name, cols in groups.items():
        Q = P[show].copy()
        Q[:, cols] = np.where(np.isnan(Q[:, cols]), np.nan, 0.0)
        contrib[name] = smooth(risk - predict_proba(model, Q)[:, 0], SMOOTH)
    names = list(contrib)
    C = np.vstack([contrib[n] for n in names])

    pc_rows = raw_pc[rows]
    F = {f: k for k, f in enumerate(FEATURES_V2)}
    ref_rms = np.sqrt(10 ** pc_rows[ref][:, :, F["log_variance"]].astype(float))
    with np.errstate(all="ignore"):
        normal_rms = np.nanmedian(ref_rms, axis=0)          # each channel's typical µV on this person's normal EEG
    return {"subject": subject, "short": short, "arm": arm, "seed": seed, "onset": onset, "timeline": W.timelines[tl_e],
            "rel_t": rel_t, "risk": risk, "ictal": ictal, "names": names, "C": C, "check": check,
            "pc": pc_rows[show], "normal_rms": normal_rms, "normal_risk": normal_risk, "rules": rules}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subject", required=True, help="a development patient, e.g. sub-034")
    ap.add_argument("--seizure", type=int, default=1, help="which of its scored seizures (in time order)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--arm", choices=ARMS, default="per_channel_slow",
                    help="per_channel_slow (D2.1, as before) or frozen (the final design)")
    args = ap.parse_args()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    plain = FuncFormatter(lambda v, _: f"{v:g}")

    R = explain(args.subject, args.seizure, args.seed, args.arm)
    rules, onset, rel_t, risk, ictal = R["rules"], R["onset"], R["rel_t"], R["risk"], R["ictal"]
    names, C, check = R["names"], R["C"], R["check"]
    args.subject = R["short"]

    # µV readouts from the unscaled per-channel features
    pc = R["pc"]                                   # n x channels x features
    F = {f: k for k, f in enumerate(FEATURES_V2)}
    present = [c for c in range(pc.shape[1]) if np.isfinite(pc[:, c, F["log_variance"]]).any()]
    amp = {b: np.sqrt(10 ** pc[:, :, F[f"logpow_{b}"]]) for b in BANDS}         # µV RMS per band
    rms = np.sqrt(10 ** pc[:, :, F["log_variance"]])                              # µV RMS overall

    out = REPO / "results" / "d2_plus" / "seizeit2_explain"
    out.mkdir(parents=True, exist_ok=True)
    tag = "" if args.arm == "per_channel_slow" else f"_{args.arm}"
    stem = out / f"{args.subject}_seizure_{onset / 3600:.1f}h{tag}".replace(".", "_")     # no dot in the stem
    with open(stem.with_suffix(".csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["seconds_from_onset", "risk", "ictal_probability"] + names)
        for k in range(len(rel_t)):
            w.writerow([round(rel_t[k], 1), round(float(risk[k]), 5), round(float(ictal[k]), 5)]
                       + [round(float(C[j, k]), 5) for j in range(len(names))])

    fig = plt.figure(figsize=(14, 4 + 2.2 * (2 + len(present))), dpi=130)
    gs = fig.add_gridspec(3 + len(present), 1, height_ratios=[1.3, 1.6] + [1.0] * len(present) + [0.9], hspace=0.55)
    ax = fig.add_subplot(gs[0])
    ax.plot(rel_t, risk, color="#9cc3ef", lw=0.8, label="preictal risk (raw)")
    ax.plot(rel_t, smooth(risk, SMOOTH), color="#2a78d6", lw=1.6, label="preictal risk, 3 min average (alarms use this)")
    ax.plot(rel_t, ictal, color="#e34948", lw=1.2, label="\"seizure happening now\" probability")
    ax.axvspan(-rules.preictal_start_s, -rules.sph_s, color="#f1c40f", alpha=0.12, label="30 min preictal period")
    ax.axvline(0, color="black", ls="--", lw=1)
    ax.set_ylim(0, 1)
    ax.set_ylabel("probability", fontsize=8)
    ax.legend(fontsize=7, loc="upper left", ncol=2, frameon=False)
    ax.set_title(f"SeizeIT2 {args.subject}, seizure at {onset / 3600:.1f} h · {args.arm} model {check}", fontsize=10)

    ax2 = fig.add_subplot(gs[1], sharex=ax)
    lim = max(np.nanmax(np.abs(C)), 0.02)
    ax2.pcolormesh(rel_t, np.arange(len(names) + 1), C[:, :-1] if C.shape[1] > 1 else C, cmap="RdBu_r",
                   vmin=-lim, vmax=lim, shading="flat")
    ax2.set_yticks(np.arange(len(names)) + 0.5)
    ax2.set_yticklabels(names, fontsize=7)
    ax2.axvline(0, color="black", ls="--", lw=1)
    ax2.set_title(f"What pushes the risk up (red) or down (blue): drop in risk when each group is reset to this "
                  f"person's normal, 3 min average, scale ±{lim:.2f}", fontsize=9)

    colors = {"delta": "#6250d6", "theta": "#2a78d6", "alpha": "#1baf7a", "beta": "#eda100", "gamma": "#e87ba4"}
    for j, c in enumerate(present):
        a = fig.add_subplot(gs[2 + j], sharex=ax)
        for b in BANDS:
            a.plot(rel_t, smooth(np.nan_to_num(amp[b][:, c]), 12), color=colors[b], lw=1, label=b)
        a.axvline(0, color="black", ls="--", lw=1)
        a.set_yscale("log")
        a.yaxis.set_major_formatter(plain)
        a.set_ylabel("µV RMS", fontsize=8)
        a.set_title(f"{CHANNELS[c].replace(' SD', '')}: amplitude in each band (1 min average)", fontsize=9)
        if j == 0:
            a.legend(fontsize=7, ncol=5, loc="upper left", frameon=False)
    a = fig.add_subplot(gs[-1], sharex=ax)
    for c in present:
        a.plot(rel_t, smooth(np.nan_to_num(rms[:, c]), 12), lw=1, label=CHANNELS[c].replace(" SD", ""))
    a.axvline(0, color="black", ls="--", lw=1)
    a.set_yscale("log")
    a.yaxis.set_major_formatter(plain)
    a.set_ylabel("µV RMS", fontsize=8)
    a.set_xlabel("seconds from seizure onset", fontsize=8)
    a.set_title("Overall amplitude per channel (RMS of each 30 s window, all frequencies, 1 min average)", fontsize=9)
    a.legend(fontsize=7, loc="upper left", frameon=False)
    a.set_xlim(-LEAD_S, AFTER_S)
    fig.savefig(stem.with_suffix(".png"), bbox_inches="tight")
    print(f"Figure: {stem.with_suffix('.png')}")

    pre = (rel_t >= -rules.preictal_start_s) & (rel_t <= -rules.sph_s)
    early = rel_t < -rules.preictal_start_s
    print("\nAverage push on the risk (risk drop when reset to normal):")
    print(f"  {'group':40s} {'60-30 min before':>18s} {'30 min before':>15s}")
    for j, n in enumerate(names):
        print(f"  {n:40s} {np.nanmean(C[j, early]) if early.any() else float('nan'):+18.3f} "
              f"{np.nanmean(C[j, pre]):+15.3f}")


if __name__ == "__main__":
    main()

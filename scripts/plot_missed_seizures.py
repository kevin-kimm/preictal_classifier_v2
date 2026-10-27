"""Which seizures does the D1 model fail to detect, and can you see why? (docs/evaluation_methods.md v1.25,
Section 14.8; the instructor's comment on the 0.865 detection AUROC, p. 4.) A characterization; the D1 model is
unchanged.

Re-runs the D1 leave-one-patient-out procedure for one seed (as scripts/diagnose_d1.py, about 3 min) and
scores every seizure on its own: the AUROC of the ictal probability for the windows lying entirely inside
that seizure against all of that patient's interictal windows. Then it plots the EEG of the three
best-detected and three worst-detected seizures side by side, with the ictal probability underneath.

Seizures shorter than one window (30 s) have no window entirely inside them, so they can't be scored this
way; they are counted separately, because they are part of why detection isn't higher.

Usage, from the repo root with .venv active:
    python scripts/plot_missed_seizures.py            seed 0

Outputs: results/d2_plus/missed_seizures.md, missed_seizures.csv and results/d2_plus/missed_seizures.png
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt
from sklearn.metrics import roc_auc_score

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from preictal.config import load_config  # noqa: E402
from preictal.data.harmonize import DERIVATIONS  # noqa: E402
from preictal.data.labels import ICTAL, INTERICTAL, LabelRules, build_timelines  # noqa: E402
from preictal.data.loaders import DEFAULT_CORRECTIONS, discover  # noqa: E402
from preictal.evaluation.lopo import make_folds, read_label_report  # noqa: E402
from preictal.features.build_features import feature_version  # noqa: E402
from preictal.models.model import predict_proba  # noqa: E402
from preictal.models.train import fit, load_windows  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

SHOW = ["Fp1-F7", "F7-T7", "T7-P7", "P7-O1", "Fp2-F8", "F8-T8", "T8-P8", "P8-O2"]
BEFORE_S, AFTER_S = 20.0, 40.0
N_SHOW = 3


def auroc(y, s):
    y = np.asarray(y, bool)
    return float(roc_auc_score(y, s)) if y.any() and (~y).any() else float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--features", type=Path, default=REPO / "data" / "processed" / "features")
    args = ap.parse_args()
    out = REPO / "results" / "d2_plus"
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    ev, length_s = cfg["evaluation"], cfg["windows"]["length_s"]
    datasets = tuple(cfg["training"]["datasets"])
    corrections = DEFAULT_CORRECTIONS.read_text() if DEFAULT_CORRECTIONS.exists() else ""
    subjects = read_label_report(REPO / "results" / "d1" / "label_report.csv")
    tl_info = json.loads((args.features / "timelines.json").read_text())
    print("Loading D1 features...")
    W = load_windows(args.features, datasets, version=feature_version(cfg, corrections), keep_per_channel=False)

    # which seizure each ictal window belongs to, and whether it lies entirely inside it
    seizure_id = np.full(len(W.y), -1)
    inside = np.zeros(len(W.y), dtype=bool)
    seizures = []
    ictal_rows = np.flatnonzero(W.y == ICTAL)
    for code in np.unique(W.timeline[ictal_rows]):
        onsets = np.sort(np.array(tl_info[W.timelines[code]]["onsets"], dtype=float))
        rows = ictal_rows[W.timeline[ictal_rows] == code]
        t = W.t_end[rows]
        k = np.searchsorted(onsets, t, side="right") - 1
        ok = k >= 0
        for j in np.unique(k[ok]):
            sid = len(seizures)
            m = rows[ok][k[ok] == j]
            seizure_id[m] = sid
            inside[m] = W.t_end[m] - length_s >= onsets[j]
            seizures.append({"id": sid, "subject": W.subjects[W.subject[m[0]]], "timeline": W.timelines[code],
                             "onset": float(onsets[j]), "ictal_windows": len(m),
                             "approx_duration_s": float(W.t_end[m].max() - onsets[j])})

    folds = make_folds(subjects, datasets, args.seed, ev["inner_validation_fraction"], ev["inner_validation_min_patients"])
    p_ictal = np.full(len(W.y), np.nan)
    it = tqdm(folds, desc="D1 folds") if tqdm else folds
    for fold in it:
        r_train, r_test = W.rows(set(fold.train)), W.rows({fold.test})
        if len(r_test) == 0:
            continue
        model = fit(W.X[r_train], W.y[r_train], W.subject[r_train], args.seed)
        p_ictal[r_test] = predict_proba(model, W.X[r_test])[:, 1]

    for s in seizures:
        own = W.subject == W.subjects.index(s["subject"])
        inter = own & (W.y == INTERICTAL) & np.isfinite(p_ictal)
        ins = (seizure_id == s["id"]) & inside & np.isfinite(p_ictal)
        s["inside_windows"] = int(ins.sum())
        s["scored"] = bool(ins.any() and inter.any())
        s["auroc"] = auroc(np.r_[np.ones(ins.sum()), np.zeros(inter.sum())], np.r_[p_ictal[ins], p_ictal[inter]]) \
            if s["scored"] else float("nan")
        s["median_ictal_p"] = float(np.median(p_ictal[ins])) if ins.any() else float("nan")
        s["dataset"] = s["subject"].split(":")[0]

    tested = {W.subjects[c] for c in np.unique(W.subject[np.isfinite(p_ictal)])}
    seizures = [s for s in seizures if s["subject"] in tested]       # only the D1 test patients have predictions
    scored = [s for s in seizures if s["scored"]]
    with open(out / "missed_seizures.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(seizures[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(seizures)
    lines = ["# Seizure detection, seizure by seizure (D1 model)", "",
             f"Generated {datetime.now().isoformat(timespec='seconds')} · seed {args.seed} · D1 model and folds, "
             "unchanged · docs/evaluation_methods.md v1.25, Section 14.8.", "",
             f"{len(seizures)} annotated seizures in the test patients; {len(scored)} have at least one window entirely "
             f"inside them; {len(seizures) - len(scored)} are shorter than one window (about 30 s) and can't be scored this way. "
             f"Seizures of the {len({s['subject'] for s in seizures})} test patients only.", "",
             "| Group | Seizures | Median per-seizure AUROC | Detected well (AUROC ≥ 0.9) | Poorly (< 0.7) |",
             "|---|---|---|---|---|"]

    def group(name, ss):
        a = np.array([s["auroc"] for s in ss])
        if len(a):
            lines.append(f"| {name} | {len(a)} | {np.median(a):.3f} | {(a >= 0.9).mean():.0%} | {(a < 0.7).mean():.0%} |")

    group("All scored seizures", scored)
    for ds in sorted({s["dataset"] for s in scored}):
        group(ds, [s for s in scored if s["dataset"] == ds])
    group("Shorter than 60 s", [s for s in scored if s["approx_duration_s"] < 60])
    group("60 s or longer", [s for s in scored if s["approx_duration_s"] >= 60])
    ranked = sorted(scored, key=lambda s: s["auroc"])
    lines += ["", "## Worst and best detected", "", "| Seizure | Patient | Onset (h into timeline) | Approx. duration (s) "
              "| Windows inside | AUROC | Median ictal probability |", "|---|---|---|---|---|---|---|"]
    for s in ranked[:10] + ranked[-5:]:
        lines.append(f"| {s['id']} | {s['subject']} | {s['onset'] / 3600:.2f} | {s['approx_duration_s']:.0f} "
                     f"| {s['inside_windows']} | {s['auroc']:.3f} | {s['median_ictal_p']:.3f} |")

    # ---------------------------------------------------------------- figure
    try:
        fig_note = draw(ranked, W, p_ictal, out, args, cfg)
        lines += ["", fig_note]
    except Exception as e:
        lines += ["", f"(figure not drawn: {e})"]
    lines += ["", "**Reading the figure.** Columns are seizures: the three the model detected worst (left) and best "
              "(right). Each shows 20 s before to 40 s after the annotated onset (dashed line), filtered 0.5–40 Hz, "
              "with the model's ictal probability below. Things to look for: whether the poorly detected seizures "
              "are visible on these scalp channels at all, whether they are short, and whether the rhythm looks like "
              "the seizures the model saw from other patients."]
    (out / "missed_seizures.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def draw(ranked, W, p_ictal, out, args, cfg):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from plot_leadup import covering, segment
    rules = LabelRules.from_config(cfg)
    picks = ranked[:N_SHOW] + ranked[-N_SHOW:]
    needed = {s["subject"] for s in picks}
    ds = tuple(sorted({s.split(":")[0] for s in needed}))
    tls = {tl.subject + "|" + "|".join(map(str, tl.key)): tl
           for tl in build_timelines(discover(REPO / "data" / "raw", datasets=ds), rules) if tl.subject in needed}
    idx = [DERIVATIONS.index(d) for d in SHOW]
    sos = butter(4, [0.5, 40], btype="bandpass", fs=256, output="sos")
    fig, axes = plt.subplots(2, len(picks), figsize=(3.2 * len(picks), 7.5),
                             gridspec_kw={"height_ratios": [4, 1]}, sharex="col")
    for col, s in enumerate(picks):
        tl = next((v for k, v in tls.items() if k.startswith(s["subject"] + "|") and
                   "|".join(map(str, v.key)) == s["timeline"]), None)
        if tl is None:
            tl = next(v for k, v in tls.items() if k.startswith(s["subject"] + "|"))
        t0, t1 = s["onset"] - BEFORE_S, s["onset"] + AFTER_S
        p = covering(tl, t0 - 5, t1 + 5)
        ax, axp = axes[0, col], axes[1, col]
        if p is None:
            ax.set_title(f"{s['subject']}\n(not in one file)", fontsize=8)
            continue
        x, fs = segment(p, t0 - 5, t1 + 5)
        x = sosfiltfilt(sos, np.nan_to_num(x[idx]), axis=1)[:, int(5 * fs):int((5 + BEFORE_S + AFTER_S) * fs)]
        tt = np.arange(x.shape[1]) / fs - BEFORE_S
        gap = max(2.5 * np.percentile(np.abs(x[:, : int(BEFORE_S * fs)]), 99), 50.0)
        for i in range(len(idx)):
            ax.plot(tt, x[i] - i * gap, color="black", linewidth=0.4)
        ax.axvline(0, color="#c0392b", linestyle="--", linewidth=0.8)
        ax.set_yticks([-i * gap for i in range(len(idx))])
        ax.set_yticklabels(SHOW if col == 0 else [], fontsize=7)
        kind = "worst" if col < N_SHOW else "best"
        ax.set_title(f"{kind}: {s['subject'].split(':')[1]}\nAUROC {s['auroc']:.2f}, ~{s['approx_duration_s']:.0f} s, "
                     f"rows {gap:.0f} µV apart",
                     fontsize=8)
        m = (W.subject == W.subjects.index(s["subject"])) & (np.array(W.timelines)[W.timeline] == s["timeline"]) \
            & (W.t_end >= t0) & (W.t_end <= t1)
        axp.plot(W.t_end[m] - s["onset"], p_ictal[m], color="#2c3e50")
        axp.axvline(0, color="#c0392b", linestyle="--", linewidth=0.8)
        axp.set_ylim(0, 1)
        axp.set_xlabel("s from onset", fontsize=8)
        if col == 0:
            axp.set_ylabel("ictal prob.", fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "missed_seizures.png", dpi=150)
    return "Figure: `results/d2_plus/missed_seizures.png`"


if __name__ == "__main__":
    main()

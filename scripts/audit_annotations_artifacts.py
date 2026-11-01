"""Annotation and artifact audit, development patients only (docs/evaluation_methods.md v1.32, Section 14.16).

A characterization: it changes no design and touches no lockbox patient. It asks three questions.

1. Are seizure onsets annotated late? A seizure detector (ictal vs normal EEG, gradient boosting on the
   frozen pooled features) is trained for each patient on the OTHER patients of the same data, so it never
   sees the audited patient's seizures. For each eligible seizure it finds the sustained detection that
   covers the onset and records when it began. A run that began >= 15 s before the annotated onset means the
   EEG already looked seizure-like, so some "preictal" windows may contain the seizure. The saved risk
   scores are then re-scored without those windows, to see whether they flatter the AUROC.
2. Are there unannotated seizures in the normal EEG? Sustained detector runs (>= 30 s) inside normal EEG,
   counted per 24 h and checked against the artifact flags.
3. How do artifacts relate to the risk? Each window is flagged when a channel's RMS amplitude is above
   5 x, or below 0.1 x, that channel's median on the patient's normal EEG. Then: artifact rates in
   preictal vs normal EEG (a label confound), AUROC without windows that had an artifact in the last
   3 min, how often the highest-risk normal windows follow an artifact, and (when alarm-calibration
   scores exist) how often false alarms follow an artifact.

Usage, from the repo root with .venv active:
    python scripts/audit_annotations_artifacts.py                       both development sets
    python scripts/audit_annotations_artifacts.py --dataset seizeit2    one of them
    python scripts/audit_annotations_artifacts.py --arm per_channel_slow   risk scores of another saved arm

Outputs (results/d2_plus/audit/):
    audit.md                     the report
    <dataset>_seizures.csv       one row per eligible seizure (detection, lead, artifacts)
    <dataset>_candidates.csv     sustained detections inside normal EEG
    <dataset>_patients.csv       per-patient rates and AUROCs
    review/<dataset>_*.png       the most-flagged seizures and candidates, for looking at by eye
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon
from sklearn.metrics import roc_auc_score

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from preictal.alarm.alarm import alarm_times  # noqa: E402
from preictal.config import load_config  # noqa: E402
from preictal.data.labels import ICTAL, INTERICTAL, PREICTAL, LabelRules  # noqa: E402
from preictal.data.loaders import DEFAULT_CORRECTIONS  # noqa: E402
from preictal.evaluation.audit import (  # noqa: E402
    CAND_MIN_P, CAND_RUN, DETECTOR_PCT, FLAG_LEAD_S, RECENT_S, artifact_flags, onset_check, recent, runs,
)
from preictal.evaluation.metrics import choose_threshold_bisect  # noqa: E402
from preictal.features.build_features import FEATURE_VERSION_V2, FEATURES_V2, feature_version  # noqa: E402
from preictal.models.model import build_model, predict_proba  # noqa: E402
from preictal.models.train import load_windows, sample_weights  # noqa: E402

OTHERS_EVERY = 6
TOP_SHARE = 0.05          # "highest-risk normal windows": each patient's top 5%
ABS_UV = 150.0            # SeizeIT2 only, reported alongside: any channel above 150 µV RMS
N_REVIEW = 6
DATASETS = ("chbmit_siena", "seizeit2")


def auroc(y, s):
    y = np.asarray(y, bool)
    return float(roc_auc_score(y, s)) if y.any() and (~y).any() else float("nan")


def scale(M, ref):
    with np.errstate(all="ignore"):
        med = np.nanmedian(ref, axis=0)
        iqr = np.maximum(np.nanpercentile(ref, 75, axis=0) - np.nanpercentile(ref, 25, axis=0), 1e-3)
    return (M - med) / iqr


def paired(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 2:
        return float("nan"), 0, int(ok.sum()), float("nan")
    d = a[ok] - b[ok]
    try:
        p = float(wilcoxon(a[ok], b[ok]).pvalue) if np.any(d != 0) else 1.0
    except ValueError:
        p = float("nan")
    return float(d.mean()), int((d > 0).sum()), int(ok.sum()), p


def load(dataset, cfg):
    """Feature windows of the development patients, with per-channel RMS (µV)."""
    sz2 = dataset == "seizeit2"
    features = REPO / "data" / "processed" / ("features_seizeit2" if sz2 else "features_v2")
    if sz2:
        from preictal.data.seizeit2 import FEATURE_CODE, VERSION_TEXT, cohort
        _, _, pool = cohort(REPO, "development")          # the lockbox's feature files are never loaded
        version = feature_version(cfg, VERSION_TEXT, FEATURE_CODE)
        datasets = ("seizeit2",)
    else:
        pool = None
        corrections = DEFAULT_CORRECTIONS.read_text() if DEFAULT_CORRECTIONS.exists() else ""
        version = feature_version(cfg, corrections, FEATURE_VERSION_V2)
        datasets = tuple(cfg["training"]["datasets"])
    W = load_windows(features, datasets, subjects=pool, version=version, keep_per_channel=True)
    rms = np.sqrt(10 ** W.per_channel[:, :, FEATURES_V2.index("log_variance")].astype(float))
    W.per_channel = None
    tl_info = json.loads((features / "timelines.json").read_text())
    return W, rms, tl_info


def detector_scores(W, seed=0):
    """Ictal probability for every window, from a model trained on the other patients (one per patient)."""
    y = W.y
    X = np.empty_like(W.X, dtype=np.float32)
    for c in range(len(W.subjects)):
        r = np.flatnonzero(W.subject == c)
        ref = r[y[r] == INTERICTAL]
        X[r] = scale(W.X[r], W.X[ref]) if len(ref) else W.X[r]
    every6 = np.round(W.t_end / 5.0).astype(np.int64) % OTHERS_EVERY == 0
    train_ok = (y == ICTAL) | ((y == INTERICTAL) & every6)
    p = np.full(len(y), np.nan)
    for c, name in enumerate(W.subjects):
        r = np.flatnonzero(W.subject == c)
        if not ((y[r] == ICTAL).any() or (y[r] == INTERICTAL).any()):
            continue
        tr = np.flatnonzero(train_ok & (W.subject != c))
        if not (y[tr] == ICTAL).any():
            continue
        m = build_model(seed)
        m.fit(X[tr], y[tr], sample_weight=sample_weights(y[tr], W.subject[tr]))
        p[r] = predict_proba(m, X[r])[:, 1]
        print(f"  detector for {name}: done", flush=True)
    return p


def saved_scores(dataset, arm, seed=0):
    d = REPO / "results" / "d2_plus" / dataset / "scores"
    plain = {f: f for f in sorted(d.glob(f"{arm}_*_seed{seed}.npz"))}
    alarms = {f: f for f in sorted(d.glob(f"{arm}_*_seed{seed}_alarms.npz"))}
    return list(plain), list(alarms)


def row_lookup(W):
    """(timeline name, t rounded to 0.1 s) -> row index."""
    return {(W.timelines[c], round(float(t), 1)): i for i, (c, t) in enumerate(zip(W.timeline, W.t_end))}


def audit(dataset, arm, cfg, rules, review_dir, raw):
    t0 = time.time()
    step_s = cfg["windows"]["step_s"]
    print(f"\n=== {dataset}: loading development windows...")
    W, rms, tl_info = load(dataset, cfg)
    y, t, tl, subj = W.y, W.t_end, W.timeline, W.subject
    order = np.lexsort((t, tl))
    print(f"  {len(y):,} windows, {len(W.subjects)} patients; training the seizure detectors...")
    p = detector_scores(W)

    # ---------------------------------------------------------------- artifact flags and detector thresholds
    high = np.zeros(len(y), bool)
    flat = np.zeros(len(y), bool)
    thr = {}
    for c in range(len(W.subjects)):
        r = np.flatnonzero(subj == c)
        ref = y[r] == INTERICTAL
        h, f = artifact_flags(rms[r], ref)
        high[r], flat[r] = h, f
        if ref.sum() >= 200 and np.isfinite(p[r][ref]).all():
            thr[c] = max(float(np.percentile(p[r][ref], DETECTOR_PCT)), CAND_MIN_P)   # and never below 0.5
    art = high | flat
    rec = recent(art, t, tl, RECENT_S)
    absuv = np.nan_to_num(rms, nan=0).max(axis=1) > ABS_UV

    # ---------------------------------------------------------------- 1. onsets
    seizures = []
    contaminated = np.zeros(len(y), bool)
    for c, cname in enumerate(W.timelines):
        info = tl_info.get(cname, {})
        sc = int(np.bincount(subj[tl == c]).argmax()) if (tl == c).any() else None
        if sc is None or sc not in thr:
            continue
        idx = order[tl[order] == c]
        for on in info.get("eligible_onsets", []):
            r = onset_check(t[idx], p[idx], thr[sc], on, step_s)
            pre_run = idx[(t[idx] >= r["run_start"] - 30.0) & (t[idx] < on)] if r["detected"] else idx[:0]
            flagged = r["detected"] and r["lead_s"] >= FLAG_LEAD_S and not r["clipped"]
            if flagged:
                contaminated[pre_run[y[pre_run] == PREICTAL]] = True
            run_rows = idx[(t[idx] >= r["run_start"]) & (t[idx] < on)] if flagged else idx[:0]
            seizures.append({"subject": W.subjects[sc], "timeline": cname, "onset_s": on,
                             "threshold": round(thr[sc], 4), "detected": r["detected"],
                             "lead_s": r["lead_s"], "clipped": r["clipped"], "peak": round(r["peak"], 4),
                             "flag_late_onset": flagged,
                             "active_throughout_5min": bool(r["detected"] and r["clipped"]),
                             "pre_onset_windows_with_artifact": round(float(art[run_rows].mean()), 3)
                             if len(run_rows) else float("nan")})

    # ---------------------------------------------------------------- 2. candidates in normal EEG
    cands = []
    for c in thr:
        r = order[subj[order] == c]
        cut = thr[c]
        for a, b in runs((y[r] == INTERICTAL) & (p[r] >= cut), t[r], tl[r], step_s, CAND_RUN):
            rows = r[a:b + 1]
            cands.append({"subject": W.subjects[c], "timeline": W.timelines[tl[rows[0]]], "start_s": float(t[rows[0]]),
                          "duration_s": float(t[rows[-1]] - t[rows[0]] + step_s), "peak": round(float(p[rows].max()), 4),
                          "share_with_artifact": round(float(art[rows].mean()), 3)})
    inter_h = {c: (y[subj == c] == INTERICTAL).sum() * step_s / 3600 for c in thr}

    # ---------------------------------------------------------------- 3. artifacts and risk
    files, alarm_files = saved_scores(dataset, arm)
    look = row_lookup(W) if files else {}
    pat = {}
    for c in thr:
        r = subj == c
        pat[W.subjects[c]] = {"subject": W.subjects[c],
                              "art_interictal": float(art[r & (y == INTERICTAL)].mean()),
                              "art_preictal": float(art[r & (y == PREICTAL)].mean()) if (r & (y == PREICTAL)).any()
                              else float("nan"),
                              "art_ictal": float(art[r & (y == ICTAL)].mean()) if (r & (y == ICTAL)).any() else float("nan"),
                              "candidates_per_24h": 24 * sum(1 for x in cands if x["subject"] == W.subjects[c])
                              / inter_h[c] if inter_h[c] else float("nan")}
    risk = np.full(len(y), np.nan)
    for f in files:
        z = np.load(f, allow_pickle=False)
        s = str(z["subject"])
        names = z["timelines"]
        rows = np.array([look.get((str(names[k]), round(float(tt), 1)), -1) for k, tt in zip(z["tl"], z["t"])])
        test = z["in_test"] & np.isin(z["label"], (PREICTAL, INTERICTAL)) & (rows >= 0)
        if not test.any():
            continue
        rr, lab, sc = rows[test], z["label"][test], z["score"][test].astype(float)
        risk[rr] = sc
        pos = lab == PREICTAL
        keep_c = ~contaminated[rr]
        keep_a = ~rec[rr]
        inter = ~pos
        top = inter & (sc >= np.quantile(sc[inter], 1 - TOP_SHARE)) if inter.sum() >= 20 else np.zeros(len(sc), bool)
        d = pat.setdefault(s, {"subject": s})
        d.update({"auroc_all": auroc(pos, sc), "auroc_without_late_onset_windows": auroc(pos[keep_c], sc[keep_c]),
                  "auroc_without_recent_artifact": auroc(pos[keep_a], sc[keep_a]),
                  "preictal_test_windows": int(pos.sum()), "contaminated_preictal": int((pos & ~keep_c).sum()),
                  "share_removed_by_artifact_rule": round(float((~keep_a).mean()), 4),
                  "recent_artifact_all_normal": float(rec[rr][inter].mean()),
                  "recent_artifact_top5_normal": float(rec[rr][top].mean()) if top.any() else float("nan")})

    alarm_rows = []
    if alarm_files:
        from d2_plus_alarms import FROZEN_SETTINGS, WARMUP_S, sequences
        sm, pe = FROZEN_SETTINGS
        refractory = cfg["alarm"]["refractory_min"] * 60
        n_cand = cfg["alarm"]["threshold_candidates"]
        kw_cal = dict(sph_s=rules.sph_s, horizon_s=rules.preictal_start_s, refractory_s=refractory,
                      smoothing=sm, persistence=pe)
        for f in alarm_files:
            z = dict(np.load(f, allow_pickle=False))
            names = z["timelines"]
            for i in np.unique(z["fold"]):
                m = z["fold"] == i
                onset = float(z["onset"][m][0])
                cm = z["cal_fold"] == i
                cal = []
                for k in np.unique(z["cal_k"][cm]):
                    kk = cm & (z["cal_k"] == k)
                    cal += sequences(z["cal_t"][kk], z["cal_tl"][kk], z["cal_label"][kk], z["cal_score"][kk].astype(float))
                th, _ = choose_threshold_bisect(cal, 5.0, step_s, n_cand, **kw_cal)
                tt, tls, lab, sc = z["t"][m], z["tl"][m], z["label"][m], z["score"][m].astype(float)
                inter = z["in_test"][m] & (lab == INTERICTAL)
                pre = z["in_pre"][m] & (tt >= onset - rules.preictal_start_s - WARMUP_S)
                for kind, sel in (("false", inter), ("true", pre)):
                    for c in np.unique(tls[sel]):
                        mm = np.flatnonzero(sel & (tls == c))
                        mm = mm[np.argsort(tt[mm], kind="stable")]
                        tl_name = str(names[int(c)])
                        for a in alarm_times(tt[mm], sc[mm], th, refractory, sm, pe):
                            if kind == "true" and not (rules.sph_s <= onset - a <= rules.preictal_start_s):
                                continue
                            row = look.get((tl_name, round(float(a), 1)), -1)
                            alarm_rows.append({"subject": str(z["subject"]), "kind": kind,
                                               "recent_artifact": bool(rec[row]) if row >= 0 else None})

    # ---------------------------------------------------------------- write per-dataset files
    out = REPO / "results" / "d2_plus" / "audit"
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in ((f"{dataset}_seizures.csv", seizures), (f"{dataset}_candidates.csv", cands),
                       (f"{dataset}_patients.csv", list(pat.values()))):
        if rows:
            keys = list(dict.fromkeys(k for r in rows for k in r))
            with open(out / name, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=keys, lineterminator="\n")
                w.writeheader()
                w.writerows(rows)

    # ---------------------------------------------------------------- review figures
    review(dataset, W, p, rms, art, risk, thr, seizures, cands, review_dir, rules, raw)

    # ---------------------------------------------------------------- summary
    S = {"dataset": dataset, "arm": arm, "patients": len(thr), "windows": len(y), "minutes": (time.time() - t0) / 60,
         "seizures": seizures, "cands": cands, "pat": pat, "alarms": alarm_rows, "n_score_files": len(files),
         "n_alarm_files": len(alarm_files), "inter_h": sum(inter_h.values()),
         "art_rate": {k: float(art[y == v].mean()) if (y == v).any() else float("nan")
                      for k, v in (("normal", INTERICTAL), ("preictal", PREICTAL), ("ictal", ICTAL))},
         "abs_rate": {k: float(absuv[y == v].mean()) if (y == v).any() else float("nan")
                      for k, v in (("normal", INTERICTAL), ("preictal", PREICTAL), ("ictal", ICTAL))},
         "high_share": float(high[art].mean()) if art.any() else float("nan")}
    return S


def review(dataset, W, p, rms, art, risk, thr, seizures, cands, review_dir, rules, raw):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, LogLocator
    review_dir.mkdir(parents=True, exist_ok=True)
    flagged = sorted([s for s in seizures if s["flag_late_onset"]], key=lambda s: -s["lead_s"])[:N_REVIEW]
    # every candidate that is mostly NOT artifact (the ones worth a look), then the longest of the rest
    clean = sorted([c for c in cands if c["share_with_artifact"] < 0.5], key=lambda c: -c["duration_s"])
    rest = sorted([c for c in cands if c["share_with_artifact"] >= 0.5], key=lambda c: -c["duration_s"])
    top_c = clean + rest[:max(0, N_REVIEW - len(clean))]
    on_before = [s for s in seizures if s.get("active_throughout_5min")][:N_REVIEW // 2]
    events = [("late_onset", s["subject"], s["timeline"], s["onset_s"], s) for s in flagged] + \
             [("on_before", s["subject"], s["timeline"], s["onset_s"], s) for s in on_before] + \
             [("candidate", c["subject"], c["timeline"], c["start_s"], c) for c in top_c]
    tl_code = {n: i for i, n in enumerate(W.timelines)}
    for kind, s_name, tl_name, T, info in events:
        c = tl_code[tl_name]
        m = (W.timeline == c) & (W.t_end >= T - 300) & (W.t_end <= T + 300)
        idx = np.flatnonzero(m)
        idx = idx[np.argsort(W.t_end[idx])]
        rel = W.t_end[idx] - T
        n_raw = 1 if (raw and dataset == "seizeit2") else 0
        fig, axes = plt.subplots(2 + n_raw, 1, figsize=(12, 5.5 + 2.5 * n_raw), dpi=120,
                                 gridspec_kw={"height_ratios": [1.2, 1.2] + [1.6] * n_raw})
        ax = axes[0]
        ax.plot(rel, p[idx], color="#e34948", lw=1.2, label="seizure detector (trained on other patients)")
        if np.isfinite(risk[idx]).any():
            ax.plot(rel, risk[idx], color="#2a78d6", lw=1, label="saved preictal risk")
        ax.axhline(thr[W.subject[idx[0]]], color="#e34948", ls=":", lw=1, label="detector threshold (99.9th pct of normal EEG, at least 0.5)")
        ax.axvline(0, color="black", ls="--", lw=1)
        for j in np.flatnonzero(art[idx]):
            ax.axvspan(rel[j] - 2.5, rel[j] + 2.5, color="#f1c40f", alpha=0.25, lw=0)
        ax.set_ylim(0, 1)
        ax.legend(fontsize=7, loc="upper left", frameon=False)
        title = (f"annotated onset; detector run began {info['lead_s']:.0f} s earlier" if kind == "late_onset" else
                 "annotated onset; detector already on 5 min before" if kind == "on_before" else
                 f"sustained detection in normal EEG, {info['duration_s']:.0f} s, "
                 f"{info['share_with_artifact']:.0%} of it flagged as artifact")
        ax.set_title(f"{dataset} {s_name.split(':')[-1]} at {T / 3600:.2f} h: {title} "
                     "(yellow: artifact-flagged windows)", fontsize=9)
        a2 = axes[1]
        for ch in range(rms.shape[1]):
            if np.isfinite(rms[idx, ch]).any():
                a2.plot(rel, rms[idx, ch], lw=0.8)
        a2.set_yscale("log")
        a2.yaxis.set_major_locator(LogLocator(subs=(1.0, 2.0, 5.0)))
        a2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        a2.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))
        a2.axvline(0, color="black", ls="--", lw=1)
        a2.set_ylabel("RMS µV per channel", fontsize=8)
        a2.set_xlabel("seconds from the event (window end times)", fontsize=8)
        if n_raw:
            try:
                before = min(max(30.0, info.get('lead_s', 0) + 15), 120.0) if kind == 'late_onset' else 30.0
                draw_raw(axes[2], s_name, T, rules, before)
            except Exception as e:  # noqa: BLE001 (a review aid; never stop the audit for it)
                axes[2].text(0.5, 0.5, f"raw EEG not available: {e}", ha="center", transform=axes[2].transAxes)
        fig.tight_layout()
        stem = f"{dataset}_{kind}_{s_name.split(':')[-1]}_{T / 3600:.2f}h".replace(".", "_")
        fig.savefig(review_dir / f"{stem}.png")
        plt.close(fig)


def draw_raw(ax, s_name, T, rules, before_s=30.0):
    """Behind-the-ear EEG (0.5-40 Hz) from before_s before T to 30 s after, SeizeIT2 development patients only."""
    from scipy.signal import butter, sosfiltfilt

    from plot_seizeit2_leadup import ROOT, read_stretch
    from preictal.data.seizeit2 import CHANNELS, discover_patient, timeline
    sub = s_name.split(":")[-1]
    tlo = timeline(discover_patient(ROOT, sub), rules)
    pl = next(q for q in tlo.placed if q.start <= T < q.end)
    x, fs, t0 = read_stretch(pl, T - before_s, T + 30)
    x = np.where(np.isnan(x), 0.0, x)
    x = sosfiltfilt(butter(4, [0.5, min(40.0, 0.45 * fs)], btype="bandpass", fs=fs, output="sos"), x, axis=1)
    gap = max(2.5 * np.percentile(np.abs(x), 99), 20.0)
    ts = t0 + np.arange(x.shape[1]) / fs - T
    for c in range(x.shape[0]):
        ax.plot(ts, x[c] - c * gap, color="black", lw=0.5)
    ax.set_yticks([-c * gap for c in range(x.shape[0])])
    ax.set_yticklabels([ch.replace(" SD", "") for ch in CHANNELS], fontsize=8)
    ax.axvline(0, color="#c0392b", ls="--", lw=1)
    ax.set_xlabel("seconds from the event", fontsize=8)
    ax.set_title(f"raw EEG, 0.5-40 Hz, channels {gap:.0f} µV apart", fontsize=9)


def fmt(x, f="{:.3f}"):
    return f.format(x) if x is not None and np.isfinite(x) else "–"


def report(results, arm):
    L = ["# Annotation and artifact audit (development patients only)", "",
         f"Generated {datetime.now().isoformat(timespec='seconds')} with `scripts/audit_annotations_artifacts.py` "
         f"· risk scores from `{arm}`, seed 0 · docs/evaluation_methods.md v1.32, Section 14.16. "
         "A characterization: nothing here changes a design, and no lockbox patient is loaded.", ""]
    for S in results:
        sz, ds = S["seizures"], S["dataset"]
        det = [s for s in sz if s["detected"]]
        fl = [s for s in sz if s["flag_late_onset"]]
        fl60 = [s for s in fl if s["lead_s"] >= 60]
        clip = [s for s in sz if s.get("active_throughout_5min")]
        leads = np.array([s["lead_s"] for s in det])
        L += [f"## {ds} ({S['patients']} patients, {S['windows']:,} windows, {S['minutes']:.0f} min)", "",
              "### 1. Seizure onsets", "",
              "| Eligible seizures | Detected (within 2 min) | Median lead of detection (s; + = before onset) "
              f"| Detection began {FLAG_LEAD_S:.0f} s to 5 min before onset | of which ≥ 60 s | Detector already on 5 min before |",
              "|---|---|---|---|---|---|",
              f"| {len(sz)} | {len(det)} ({len(det) / max(len(sz), 1):.0%}) | {fmt(np.median(leads) if len(leads) else np.nan, '{:.0f}')} "
              f"| {len(fl)} ({len(fl) / max(len(sz), 1):.0%}) | {len(fl60)} | {len(clip)} |", "",
              "A detection that begins seconds to a minute or two before the annotated onset suggests the onset was "
              "marked late. One that is already on 5 min before is more likely a change of state, an artifact or a "
              "genuine pre-seizure change, so those aren't counted as late onsets. Either way, only a look at the "
              "EEG (the figures in `review/`) can tell which.", ""]
        if fl:
            share_art = np.nanmean([s["pre_onset_windows_with_artifact"] for s in fl])
            L.append(f"In the flagged seizures, {fmt(share_art, '{:.0%}')} of the pre-onset detection windows were "
                     "also flagged as artifact (a run caused by movement looks the same to the detector).")
            L.append("")
        P = list(S["pat"].values())
        a_all = [x.get("auroc_all", np.nan) for x in P]
        a_c = [x.get("auroc_without_late_onset_windows", np.nan) for x in P]
        a_a = [x.get("auroc_without_recent_artifact", np.nan) for x in P]
        n_pre = sum(x.get("preictal_test_windows", 0) for x in P)
        n_con = sum(x.get("contaminated_preictal", 0) for x in P)
        if S["n_score_files"]:
            dm, nh, n, pv = paired(a_c, a_all)
            L += [f"**Does EEG just before the annotated onset drive the result?** {n_con:,} of {n_pre:,} preictal test windows "
                  f"({n_con / max(n_pre, 1):.1%}) lie in or just before a flagged pre-onset detection. Without them, "
                  f"mean AUROC is {fmt(np.nanmean(a_c))} against {fmt(np.nanmean(a_all))} ({dm:+.3f}; "
                  f"higher without them in {nh} of {n}; p = {fmt(pv, '{:.2g}')}). Rule fixed in advance: a drop of 0.01 or more means "
                  f"seizure-like EEG just before the annotated onset contributes to the result, either because onsets "
                  f"are marked late (flattering) or because the change is a real early sign (the review decides). "
                  f"**Reading: {'it contributes; review the flagged seizures' if np.isfinite(dm) and dm <= -0.01 else 'no evidence that it does'}.**", ""]
        else:
            L += ["No saved risk scores for this arm, so the AUROC checks were skipped.", ""]
        c = S["cands"]
        ca = [x for x in c if x["share_with_artifact"] >= 0.5]
        L += ["### 2. Possible unannotated seizures in normal EEG", "",
              f"Sustained detections (≥ {CAND_RUN * 5} s at or above the patient's detector threshold) "
              f"inside normal EEG: **{len(c)}** over {S['inter_h']:.0f} h "
              f"({24 * len(c) / max(S['inter_h'], 1e-9):.2f} per 24 h); {len(ca)} of them are mostly artifact-flagged. "
              "The longest are in `review/` for a look by eye; a detection isn't a seizure until someone reading "
              "the EEG says so.", ""]
        ar, au = S["art_rate"], S["abs_rate"]
        art_i = [x.get("art_interictal", np.nan) for x in P]
        art_p = [x.get("art_preictal", np.nan) for x in P]
        dm2, nh2, n2, p2 = paired(art_p, art_i)
        ratio = ar["preictal"] / ar["normal"] if ar["normal"] > 0 else np.nan
        L += ["### 3. Artifacts", "",
              f"Windows flagged (a channel above 5 x or below 0.1 x its normal median; "
              f"{fmt(S['high_share'], '{:.0%}')} of flags are 'above'):", "",
              "| | Normal EEG | Preictal | Ictal |", "|---|---|---|---|",
              f"| Flagged as artifact | {fmt(ar['normal'], '{:.1%}')} | {fmt(ar['preictal'], '{:.1%}')} "
              f"| {fmt(ar['ictal'], '{:.1%}')} |"]
        if ds == "seizeit2":
            L.append(f"| Any channel above {ABS_UV:.0f} µV RMS | {fmt(au['normal'], '{:.1%}')} | "
                     f"{fmt(au['preictal'], '{:.1%}')} | {fmt(au['ictal'], '{:.1%}')} |")
        L += ["", f"Seizures themselves are often flagged (high amplitude), which is expected. **Label confound check:** "
              f"preictal windows are flagged {fmt(ratio, '{:.2f}')} times as often as normal EEG (per patient "
              f"{dm2:+.3f}, higher in {nh2} of {n2}, p = {fmt(p2, '{:.2g}')}). Rule fixed in advance: 1.5 times or "
              f"more with p < 0.05 means artifacts may be part of what the model learned as 'preictal'. **Reading: "
              f"{'possible confound' if np.isfinite(ratio) and ratio >= 1.5 and np.isfinite(p2) and p2 < 0.05 else 'no evidence of a confound'}.**", ""]
        if S["n_score_files"]:
            dm3, nh3, n3, p3 = paired(a_a, a_all)
            share = np.nanmean([x.get("share_removed_by_artifact_rule", np.nan) for x in P])
            r_all = np.nanmean([x.get("recent_artifact_all_normal", np.nan) for x in P])
            r_top = np.nanmean([x.get("recent_artifact_top5_normal", np.nan) for x in P])
            L += [f"**Risk and artifacts.** Dropping test windows with an artifact in the last 3 min "
                  f"({fmt(share, '{:.1%}')} of them) changes mean AUROC from {fmt(np.nanmean(a_all))} to "
                  f"{fmt(np.nanmean(a_a))} ({dm3:+.3f}, higher in {nh3} of {n3}, p = {fmt(p3, '{:.2g}')}). "
                  f"In normal EEG, {fmt(r_all, '{:.1%}')} of windows follow a recent artifact, against "
                  f"{fmt(r_top, '{:.1%}')} of each patient's top 5% by risk (lift {fmt(r_top / r_all if r_all else np.nan, '{:.1f}')}x).", ""]
        al = S["alarms"]
        if al:
            fa = [a for a in al if a["kind"] == "false" and a["recent_artifact"] is not None]
            ta = [a for a in al if a["kind"] == "true" and a["recent_artifact"] is not None]
            base = np.nanmean([x.get("recent_artifact_all_normal", np.nan) for x in P])
            f_share = np.mean([a["recent_artifact"] for a in fa]) if fa else np.nan
            t_share = np.mean([a["recent_artifact"] for a in ta]) if ta else np.nan
            lift = f_share / base if base else np.nan
            L += [f"**Alarms** (frozen settings, ≤ 5 per 24 h target, {S['n_alarm_files']} patients with alarm "
                  f"calibration): {fmt(f_share, '{:.0%}')} of {len(fa)} false alarms and {fmt(t_share, '{:.0%}')} "
                  f"of {len(ta)} true alarms had an artifact in the 3 min before, against {fmt(base, '{:.0%}')} of "
                  f"normal EEG overall (false-alarm lift {fmt(lift, '{:.1f}')}x). Rule fixed in advance: a lift of "
                  f"1.5x or more makes an artifact gate worth pre-registering for v3. **Reading: "
                  f"{'worth testing' if np.isfinite(lift) and lift >= 1.5 else 'not supported here'}.**", ""]
        else:
            L += [f"No alarm-calibration scores (`{arm}_*_seed0_alarms.npz`) for this dataset, so the alarm-level "
                  "check was skipped; `scripts/run_d2_plus.py --arm frozen --alarms --seeds 0` makes them.", ""]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", nargs="+", choices=DATASETS, default=list(DATASETS))
    ap.add_argument("--arm", default="frozen", help="saved risk scores to audit (seed 0)")
    ap.add_argument("--no-raw", action="store_true", help="skip the raw-EEG panel in SeizeIT2 review figures")
    args = ap.parse_args()
    cfg = load_config()
    rules = LabelRules.from_config(cfg)
    out = REPO / "results" / "d2_plus" / "audit"
    results = [audit(ds, args.arm, cfg, rules, out / "review", not args.no_raw) for ds in args.dataset]
    md = report(results, args.arm)
    name = "audit.md" if len(args.dataset) == 2 else f"audit_{args.dataset[0]}.md"
    (out / name).write_text(md)
    print("\n" + md)
    print(f"Report: {out / name}")


if __name__ == "__main__":
    main()

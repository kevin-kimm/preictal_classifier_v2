"""Where the simulation's false alarms come from (docs/evaluation_methods.md v1.21, a v3 diagnostic).

Reads the alarm log written by
    python scripts/run_learning_curve.py --adaptive --log-alarms --tag _breakdown
and reports, side by side for fixed and adaptive thresholds:

  1. false alarms per 24 h by learning stage (seizures learned) and by time since the last
     retraining (0-6 h, 6-24 h, more than 24 h)
  2. how concentrated they are: the share from the 3 patients with the most, and each
     patient's rate
  3. whether they coincide with movement or muscle activity in the 5 min before the alarm:
     SeizeIT2's accelerometer (mov) and EMG recordings where present, and an EEG muscle index
     (30-45 Hz power on the behind-the-ear channels) that is always available. Each is compared
     with the same patient's distribution over randomly sampled normal EEG ("high" = above
     that patient's 90th percentile, so 10% would be expected by chance)

Changes no model, threshold or alarm rule. SeizeIT2 development patients only.

Usage, from the repo root with .venv active:
    python scripts/breakdown_false_alarms.py

Outputs: results/seizeit2_dev/false_alarm_breakdown.md and false_alarm_signal_quality.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt, welch
from scipy.stats import binomtest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from preictal.data.edf import read_header, read_signals  # noqa: E402
from preictal.data.labels import INTERICTAL  # noqa: E402
from preictal.data.seizeit2 import read_bte  # noqa: E402

SEG_S = 300.0
STAGES = ["1", "2", "3", "4", "5+"]
SINCE = [("0–6 h", "inter_h_0_6", 0, 6), ("6–24 h", "inter_h_6_24", 6, 24), ("> 24 h", "inter_h_24p", 24, 1e9)]


def sibling(eeg_path: Path, kind: str) -> Path:
    """The accelerometer (mov) or EMG file recorded alongside an EEG file, if it exists."""
    return eeg_path.parent.parent / kind / eeg_path.name.replace("_eeg.edf", f"_{kind}.edf")


def read_span(path: Path, end_s: float, pick):
    """SEG_S seconds ending at end_s from the channels chosen by pick(labels); (signals, fs) or None."""
    if not path.exists():
        return None
    hdr = read_header(path)
    idx = pick(hdr.labels)
    if not idx:
        return None
    a, b = max(0.0, end_s - SEG_S), min(end_s, hdr.duration_s)
    if b - a < 60:
        return None
    r0, r1 = int(a // hdr.record_s), min(hdr.n_records, int(np.ceil(b / hdr.record_s)))
    sig = read_signals(hdr, idx, r0, r1 - r0)
    fs = hdr.fs(idx[0])
    i0 = int(round((a - r0 * hdr.record_s) * fs))
    n = int(round((b - a) * fs))
    return np.array([s[i0:i0 + n] for s in sig]), fs


def measures(eeg_path: Path, end_s: float) -> dict:
    out = {"eeg_muscle": np.nan, "movement": np.nan, "emg": np.nan}
    try:
        hdr = read_header(eeg_path)
        a = max(0.0, end_s - SEG_S)
        r0 = int(a // hdr.record_s)
        x, present, fs, _ = read_bte(eeg_path, r0, int(np.ceil(SEG_S / hdr.record_s)) + 1)
        i0 = int(round((a - r0 * hdr.record_s) * fs))
        x = x[present][:, i0:i0 + int(SEG_S * fs)]
        if x.shape[1] > fs * 60:
            f, pxx = welch(np.nan_to_num(x), fs=fs, nperseg=int(2 * fs), axis=1)
            band = (f >= 30) & (f <= 45)
            out["eeg_muscle"] = float(np.mean(np.log10(pxx[:, band].mean(axis=1) + 1e-12)))
    except Exception:
        pass
    mov = read_span(sibling(eeg_path, "mov"), end_s,
                    lambda labels: [i for i, l in enumerate(labels) if "acc" in l.lower()][:3]
                    or [i for i, l in enumerate(labels) if "annot" not in l.lower()][:3])
    if mov is not None:
        sig, _ = mov
        mag = np.sqrt(np.sum(np.nan_to_num(sig) ** 2, axis=0))
        out["movement"] = float(np.log10(np.std(mag) + 1e-9))
    emg = read_span(sibling(eeg_path, "emg"), end_s,
                    lambda labels: [i for i, l in enumerate(labels) if "emg" in l.lower()][:1]
                    or [i for i, l in enumerate(labels) if "annot" not in l.lower()][:1])
    if emg is not None:
        sig, fs = emg
        x = np.nan_to_num(sig[0])
        if fs >= 100:
            x = sosfiltfilt(butter(4, 20, btype="highpass", fs=fs, output="sos"), x)
        out["emg"] = float(np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="_breakdown")
    ap.add_argument("--samples", type=int, default=150, help="normal-EEG samples per patient for the reference")
    ap.add_argument("--features", type=Path, default=REPO / "data" / "processed" / "features_seizeit2")
    args = ap.parse_args()
    res = REPO / "results" / "seizeit2_dev"
    log = list(csv.DictReader(open(res / f"alarm_log{args.tag}.csv")))
    steps = list(csv.DictReader(open(res / f"learning_curve{args.tag}.csv")))
    raw_root = REPO / "data" / "raw"
    for r in log:
        r["k"], r["false"] = int(r["k"]), r["false"] == "True"
        for c in ("t", "s_into_recording", "h_since_retraining", "target"):
            r[c] = float(r[c])
    fas = [r for r in log if r["false"] and r["k"] >= 1]
    after = [s for s in steps if int(s["k"]) >= 1]
    configs = [(m, mode, tg) for m in ("personal", "general") for mode in ("fixed", "adaptive") for tg in (5.0, 1.0)]
    name = {"personal": "learning device", "general": "never learns"}

    def hours_key(m, mode, tg):
        return f"hours_{m}_{tg:g}" + ("_adaptive" if mode == "adaptive" else "")

    lines = ["# False-alarm breakdown (v3 development diagnostic)", "",
             "Forward-in-time simulation, SeizeIT2 development patients, steps after at least one learned seizure "
             "(docs/evaluation_methods.md v1.21). Rates are false alarms per 24 h of monitored normal EEG.", ""]

    # 1. learning stage and time since retraining
    lines += ["## 1. By learning stage and time since retraining", "",
              "| Model | Thresholds | Target | " + " | ".join(f"{s} learned" for s in STAGES) + " | "
              + " | ".join(f"{lab} after retraining" for lab, *_ in SINCE) + " |",
              "|---|---|---|" + "---|" * (len(STAGES) + len(SINCE))]
    for m, mode, tg in configs:
        cells = []
        for s in STAGES:
            ks = [st for st in after if (str(int(st["k"])) == s or (s == "5+" and int(st["k"]) >= 5))]
            h = sum(float(st[hours_key(m, mode, tg)] or 0) for st in ks)
            n = sum(1 for r in fas if r["model"] == m and r["thresholds"] == mode and r["target"] == tg
                    and (str(r["k"]) == s or (s == "5+" and r["k"] >= 5)))
            cells.append(f"{24 * n / h:.1f}" if h else "–")
        for lab, col, lo, hi in SINCE:
            h = sum(float(st[col] or 0) for st in after)
            n = sum(1 for r in fas if r["model"] == m and r["thresholds"] == mode and r["target"] == tg
                    and lo <= r["h_since_retraining"] < hi)
            cells.append(f"{24 * n / h:.1f}" if h else "–")
        lines.append(f"| {name[m]} | {mode} | ≤ {tg:g} | " + " | ".join(cells) + " |")

    # 2. concentration across patients
    lines += ["", "## 2. Which patients", "",
              "| Model | Thresholds | Target | False alarms | Share from the top 3 patients | Patients with any | "
              "Highest per-patient rate (per 24 h) |", "|---|---|---|---|---|---|---|"]
    per_patient_rows, consistency = [], []
    for m, mode, tg in configs:
        counts, hours = defaultdict(int), defaultdict(float)
        for r in fas:
            if r["model"] == m and r["thresholds"] == mode and r["target"] == tg:
                counts[r["subject"]] += 1
        for st in after:
            hours[st["subject"]] += float(st[hours_key(m, mode, tg)] or 0)
        total = sum(counts.values())
        expected = sum(int(float(st[hours_key(m, mode, tg).replace("hours_", "fa_")] or 0)) for st in after)
        if total != expected:
            print(f"WARNING: {name[m]} {mode} ≤{tg:g}: {total} logged false alarms but the simulation counted {expected}")
        consistency.append(total == expected)
        top3 = sum(sorted(counts.values(), reverse=True)[:3])
        rates = {s: 24 * counts[s] / hours[s] for s in hours if hours[s] > 0}
        worst = max(rates.items(), key=lambda kv: kv[1]) if rates else ("–", float("nan"))
        lines.append(f"| {name[m]} | {mode} | ≤ {tg:g} | {total} | {top3 / total:.0%} | {len(counts)} | "
                     f"{worst[1]:.1f} ({worst[0]}) |" if total else f"| {name[m]} | {mode} | ≤ {tg:g} | 0 | – | 0 | – |")
        if (m, mode, tg) == ("personal", "adaptive", 5.0):
            per_patient_rows = sorted(((s, counts[s], hours[s], rates.get(s, float("nan"))) for s in hours),
                                      key=lambda x: -x[3] if not np.isnan(x[3]) else 0)
    lines += ["", f"Check: the logged false alarms {'match' if all(consistency) else 'do NOT match'} the simulation's "
              "own counts in every configuration.",
              "", "Per patient, learning device with adaptive thresholds (≤ 5):", "",
              "| Patient | False alarms | Monitored normal EEG (h) | Per 24 h |", "|---|---|---|---|"]
    lines += [f"| {s} | {c} | {h:.1f} | {r:.1f} |" for s, c, h, r in per_patient_rows]

    # 3. signal quality around false alarms, against each patient's normal EEG
    print("Measuring signal quality around false alarms and in sampled normal EEG...")
    from preictal.config import load_config
    from preictal.data.seizeit2 import FEATURE_CODE, VERSION_TEXT
    from preictal.features.build_features import feature_version
    from preictal.models.train import load_windows
    W = load_windows(args.features, ("seizeit2",), version=feature_version(load_config(), VERSION_TEXT, FEATURE_CODE),
                     keep_per_channel=False)
    rng = np.random.default_rng(0)
    reference = defaultdict(lambda: defaultdict(list))
    patients = sorted({r["subject"] for r in fas})
    for s in patients:
        code = W.subjects.index(s)
        rows = np.flatnonzero((W.subject == code) & (W.y == INTERICTAL))
        for g in rng.choice(rows, size=min(args.samples, len(rows)), replace=False):
            path = raw_root / W.recordings[W.recording[g]]
            for key, v in measures(path, float(W.starts[g] + 30)).items():
                reference[s][key].append(v)
    keys = ("eeg_muscle", "movement", "emg")
    sq_rows = []
    uniq = {}
    for r in fas:
        uid = (r["recording"], r["s_into_recording"])
        if uid not in uniq:
            uniq[uid] = measures(raw_root / r["recording"], r["s_into_recording"])
        sq_rows.append({**{c: r[c] for c in ("subject", "k", "model", "thresholds", "target", "t")}, **uniq[uid]})
    with open(res / "false_alarm_signal_quality.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(sq_rows[0]) if sq_rows else ["subject"], lineterminator="\n")
        w.writeheader()
        w.writerows(sq_rows)
    lines += ["", "## 3. Movement and muscle activity in the 5 min before each false alarm", "",
              "\"High\" means above that patient's 90th percentile in sampled normal EEG, so about 10% of false "
              "alarms would be high by chance. Measures that couldn't be read (a missing file) are left out.", "",
              "| Model | Thresholds | Target | " + " | ".join(f"High {k.replace('_', ' ')} (n)" for k in keys) + " |",
              "|---|---|---|" + "---|" * len(keys)]
    p90 = {s: {k: np.nanpercentile(v, 90) if np.isfinite(v).any() else np.nan for k, v in reference[s].items()}
           for s in reference}
    for m, mode, tg in configs:
        cells = []
        for k in keys:
            flags = [row[k] > p90[row["subject"]][k] for row in sq_rows
                     if row["model"] == m and row["thresholds"] == mode and row["target"] == tg
                     and np.isfinite(row[k]) and np.isfinite(p90[row["subject"]][k])]
            if flags:
                pv = binomtest(int(sum(flags)), len(flags), 0.1, alternative="greater").pvalue
                cells.append(f"{np.mean(flags):.0%} (n={len(flags)}, p={pv:.2g})")
            else:
                cells.append("not available")
        lines.append(f"| {name[m]} | {mode} | ≤ {tg:g} | " + " | ".join(cells) + " |")
    found = {k: sum(np.isfinite(v).sum() for s in reference for kk, v in reference[s].items() if kk == k) for k in keys}
    lines += ["", f"Readable reference samples: EEG muscle {found['eeg_muscle']}, movement {found['movement']}, "
              f"EMG {found['emg']} (of {sum(len(reference[s]['eeg_muscle']) for s in reference)})."]

    (res / "false_alarm_breakdown.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nReport: {res / 'false_alarm_breakdown.md'}")


if __name__ == "__main__":
    main()

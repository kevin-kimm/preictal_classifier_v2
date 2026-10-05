"""A PDF showing how every patient was categorized, built from the project's own result files.

  page 1   flow diagram: from all patients in each dataset to the groups each test used
  page 2   the rules behind each category
  pages 3+ one row per patient: CHB-MIT and Siena, then SeizeIT2 (TUSZ as a summary, since
           its 675 patients all have the same role)

Every number is read from files in the repository (label report, personalized results, the
SeizeIT2 split, the feasibility report, lockbox results), nothing is typed in. A file that
isn't there shows as "not found".

Usage, from the repo root with .venv active:
    python scripts/patient_categories_pdf.py

Output: results/figures/patient_categories.pdf
"""

from __future__ import annotations

import csv
import re
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

R = REPO / "results"
INK, MUTED = "#1f2933", "#6b7785"
FILL = {"all": "#edf2f7", "role": "#e6fffa", "test": "#ebf8ff", "pers": "#faf5ff", "fa": "#fff5f5",
        "dev": "#fffaf0", "lock": "#f0fff4"}


def read_csv(path):
    return list(csv.DictReader(open(path))) if path.exists() else None


def subjects_in(path):
    rows = read_csv(path)
    return sorted({r["subject"] for r in rows}) if rows else None


def n(x):
    return "not found" if x is None else str(len(x) if not isinstance(x, int) else x)


def box(ax, x, y, w, h, title, body, kind):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.012",
                                fc=FILL[kind], ec="#a0aec0", lw=0.9))
    ax.text(x + 0.012, y + h - 0.016, title, fontsize=9.2, weight="bold", va="top", color=INK)
    ax.text(x + 0.012, y + h - 0.045, "\n".join(textwrap.wrap(body, int(w * 112))), fontsize=7.6, va="top",
            color=INK, linespacing=1.25)


def arrow(ax, x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=9, color="#718096", lw=0.9))


def table_pages(pdf, title, header, rows, widths, per_page=34, note=""):
    for start in range(0, max(len(rows), 1), per_page):
        chunk = rows[start:start + per_page]
        fig = plt.figure(figsize=(11, 8.5))
        fig.suptitle(f"{title}" + (f" ({start // per_page + 1})" if len(rows) > per_page else ""),
                     x=0.05, ha="left", fontsize=14, color=INK)
        if note:
            fig.text(0.05, 0.915, note, fontsize=8, color=MUTED)
        ax = fig.add_axes([0.04, 0.04, 0.92, 0.85])
        ax.axis("off")
        tab = ax.table(cellText=chunk or [["–"] * len(header)], colLabels=header, colWidths=widths,
                       loc="upper left", cellLoc="left")
        tab.auto_set_font_size(False)
        tab.set_fontsize(7.4)
        tab.scale(1, 1.18)
        for (r, c), cell in tab.get_celld().items():
            cell.set_edgecolor("#cbd5e0")
            if r == 0:
                cell.set_facecolor("#2d3748")
                cell.get_text().set_color("white")
                cell.get_text().set_weight("bold")
            elif chunk and chunk[r - 1][-1].startswith("✓"):
                cell.set_facecolor("#f0fff4")
        pdf.savefig(fig)
        plt.close(fig)


def main():
    label = read_csv(R / "d1" / "label_report.csv")
    pers4 = subjects_in(R / "d2" / "personalized_dev_ctx10.csv")
    pers1 = subjects_in(R / "d2" / "personalized_sens_gap1h.csv")
    split = None
    split_file = REPO / "configs" / "seizeit2_split.yaml"
    if split_file.exists():
        import yaml
        split = yaml.safe_load(split_file.read_text())
    feas = {}
    if (R / "seizeit2_dev" / "feasibility.md").exists():
        for line in (R / "seizeit2_dev" / "feasibility.md").read_text().splitlines():
            if line.startswith("| seizeit2:"):
                c = [x.strip() for x in line.strip("|").split("|")]
                feas[c[0]] = {"files": c[1], "eeg_h": c[2], "seizures": c[3], "events": c[4], "eligible": c[5],
                              "interictal_h": c[7], "qualifies": c[8] == "yes"}
    dry = subjects_in(R / "seizeit2_dev" / "personalized_seizeit2_dev.csv")
    curve = subjects_in(R / "seizeit2_dev" / "learning_curve.csv")
    lock_scored = subjects_in(R / "lockbox" / "seizeit2_lockbox_auroc.csv")
    lock_q, alarm_subset = None, None
    if (R / "lockbox" / "seizeit2_lockbox_auroc.md").exists():
        m = re.search(r"· (\d+) patients ·", (R / "lockbox" / "seizeit2_lockbox_auroc.md").read_text())
        lock_q = int(m.group(1)) if m else None
    if (R / "lockbox" / "seizeit2_lockbox_alarms.md").exists():
        m = re.search(r"\(seed 0, evaluation methods v1\.18\): (.+?)\.\s*$",
                      (R / "lockbox" / "seizeit2_lockbox_alarms.md").read_text(), re.M)
        alarm_subset = sorted(s.strip() for s in m.group(1).split(",")) if m else None
    if label is None:
        sys.exit("results/d1/label_report.csv not found: run scripts/build_labels.py first")

    by_ds = {}
    for r in label:
        by_ds.setdefault(r["dataset"], []).append(r)
    scalp = [r for r in label if r["dataset"] in ("chbmit", "siena")]
    lopo = [r for r in scalp if r["eligible_test_patient"] == "True"]
    fa_only = [r for r in label if r["role"] != "train_test"]
    dev = [f"seizeit2:{s}" for s in split["development"]] if split else None
    lock = [f"seizeit2:{s}" for s in split["lockbox"]] if split else None
    dev_q = [s for s, v in feas.items() if v["qualifies"]] if feas else None

    out = R / "figures" / "patient_categories.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(out) as pdf:
        # ---------------- page 1: flow diagram
        fig = plt.figure(figsize=(11, 8.5))
        fig.suptitle("How patients were categorized", x=0.05, ha="left", fontsize=15, color=INK)
        fig.text(0.05, 0.925, "Counts are read from the project's result files. Boxes on the left: scalp EEG (D1, D2). "
                 "Boxes on the right: SeizeIT2 wearable EEG (lockbox, v3).", fontsize=8.5, color=MUTED)
        ax = fig.add_axes([0.02, 0.02, 0.96, 0.88])
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
        ds_line = ", ".join(f"{d}: {len(v)}" for d, v in sorted(by_ds.items()))
        box(ax, 0.01, 0.84, 0.46, 0.13, f"Scalp EEG datasets: {len(label)} patients",
            f"{ds_line}. Every recording labeled into preictal, ictal, interictal and excluded windows.", "all")
        box(ax, 0.01, 0.64, 0.22, 0.15, f"Train and test pool: {len(scalp)}",
            "CHB-MIT and Siena (role train_test): used to train models and as test patients.", "role")
        box(ax, 0.25, 0.64, 0.22, 0.15, f"False-alarm only: {len(fa_only)}",
            "Datasets with role false_alarm (TUSZ" + (", mental arithmetic" if "mental_arith" in by_ds else "")
            + "): never trained on; used to count false alarms on new people.", "fa")
        box(ax, 0.01, 0.43, 0.22, 0.16, f"Cross-patient test patients: {len(lopo)}",
            "At least 1 eligible seizure and 1 h of interictal EEG. Each held out once (leave one patient out; "
            "D1, D2).", "test")
        box(ax, 0.01, 0.21, 0.22, 0.17, f"Personalized test patients: {n(pers4)}",
            "At least 2 eligible seizures and 1 h of interictal windows: one seizure held out at a time "
            "(patient-specific, personalized, frozen design).", "pers")
        box(ax, 0.25, 0.21, 0.22, 0.17, f"1 h sensitivity analysis: {n(pers1)}",
            "The same rule with every label using a 1 h gap instead of 4 h; brings in patients whose seizures "
            "are close together.", "pers")
        arrow(ax, 0.12, 0.84, 0.12, 0.79); arrow(ax, 0.36, 0.84, 0.36, 0.79)
        arrow(ax, 0.12, 0.64, 0.12, 0.59); arrow(ax, 0.12, 0.43, 0.12, 0.38); arrow(ax, 0.20, 0.43, 0.30, 0.38)

        box(ax, 0.53, 0.84, 0.46, 0.13, f"SeizeIT2 (wearable): {n(dev and dev + lock)} patients",
            "Split once by patient ID only (seed 0), before anyone looked at the data.", "all")
        box(ax, 0.53, 0.64, 0.22, 0.15, f"Development: {n(dev)}",
            "Used to build and check the SeizeIT2 adapter, the dry run, and all v3 tuning (Phase A).", "dev")
        box(ax, 0.77, 0.64, 0.22, 0.15, f"Lockbox: {n(lock)}",
            "Sealed for v2's single final test; held-out patients for v3's Phase B.", "lock")
        box(ax, 0.53, 0.43, 0.22, 0.16, f"Qualify for personalized tests: {n(dev_q)}",
            "At least 2 eligible seizures (lead-up inside their own file) and 1 h of interictal EEG.", "dev")
        box(ax, 0.77, 0.43, 0.22, 0.16, f"Qualify: {n(lock_q)}; scored: {n(lock_scored)}",
            "Lockbox AUROC test (v2 frozen design). Scored = at least one usable fold.", "lock")
        box(ax, 0.53, 0.21, 0.22, 0.17, f"Dry run scored: {n(dry)}; simulation: {n(curve)}",
            "Dry run of the frozen design; and patients with at least one step in the forward-in-time "
            "simulation (v3).", "dev")
        box(ax, 0.77, 0.21, 0.22, 0.17, f"Lockbox alarm subset: {n(alarm_subset)}",
            "Drawn at random (seed 0) from the scored patients for the alarm part, before any alarm result "
            "was seen (v1.18).", "lock")
        arrow(ax, 0.64, 0.84, 0.64, 0.79); arrow(ax, 0.88, 0.84, 0.88, 0.79)
        arrow(ax, 0.64, 0.64, 0.64, 0.59); arrow(ax, 0.88, 0.64, 0.88, 0.59)
        arrow(ax, 0.64, 0.43, 0.64, 0.38); arrow(ax, 0.88, 0.43, 0.88, 0.38)
        ax.text(0.01, 0.12, "Why patients drop out: a seizure is eligible only if at least 90% of its 30 min lead-up was "
                "recorded (SeizeIT2: inside its own file), and seizures less than 30 min apart count as one event. "
                "Interictal EEG must be at least 4 h from any seizure. Patients without enough of either can't be "
                "tested in that way.", fontsize=8, color=MUTED, wrap=True)
        pdf.savefig(fig)
        plt.close(fig)

        # ---------------- page 2: rules
        rules = [
            ("Preictal window", "30 min to 5 s before a seizure onset (the warning period)."),
            ("Ictal window", "During a seizure."),
            ("Interictal window", "At least 4 h from any seizure (normal EEG)."),
            ("Excluded window", "Everything else (too close to a seizure to be normal, not in a warning period)."),
            ("Event", "Seizures less than 30 min apart are grouped; the first one's onset counts."),
            ("Eligible event", "At least 90% of its 30 min lead-up is recorded (SeizeIT2: inside the seizure's own file)."),
            ("Role train_test", "CHB-MIT and Siena patients: can be trained on and tested."),
            ("False-alarm only", "TUSZ patients (and the mental arithmetic set): no eligible seizures; used only to "
                                 "measure false alarms on people the model never saw."),
            ("Cross-patient test patient", "Role train_test, at least 1 eligible event and 1 h of interictal EEG. "
                                           "Tested by leaving that patient out (D1, D2)."),
            ("Personalized test patient", "At least 2 eligible events and 1 h of interictal windows. Tested by "
                                          "leaving one seizure out at a time, with buffers (D2, frozen design)."),
            ("SeizeIT2 development", "25 patients drawn by ID only (seed 0): adapter, dry run, all v3 tuning."),
            ("SeizeIT2 lockbox", "The other 100: v2's single final test; v3's held-out Phase B patients."),
            ("Qualifies (SeizeIT2)", "At least 2 eligible events and 1 h of interictal EEG."),
            ("Scored", "Qualified and had at least one fold with usable training data."),
            ("Simulation patient (v3)", "Has at least one forward-in-time step (calibration, or a retraining "
                                        "before the next seizure)."),
        ]
        fig = plt.figure(figsize=(11, 8.5))
        fig.suptitle("The rules behind each category", x=0.05, ha="left", fontsize=15, color=INK)
        ax = fig.add_axes([0.04, 0.04, 0.92, 0.86])
        ax.axis("off")
        tab = ax.table(cellText=[[a, "\n".join(textwrap.wrap(b, 105))] for a, b in rules],
                       colLabels=["Category", "Rule"], colWidths=[0.22, 0.78], loc="upper left", cellLoc="left")
        tab.auto_set_font_size(False)
        tab.set_fontsize(8.2)
        for (r, c), cell in tab.get_celld().items():
            cell.set_edgecolor("#cbd5e0")
            cell.set_height(0.055 if r else 0.04)
            if r == 0:
                cell.set_facecolor("#2d3748")
                cell.get_text().set_color("white")
                cell.get_text().set_weight("bold")
        pdf.savefig(fig)
        plt.close(fig)

        # ---------------- per-patient tables
        rows = []
        for r in sorted(scalp, key=lambda r: (r["dataset"], r["subject"])):
            s = r["subject"]
            used = []
            if r["eligible_test_patient"] == "True":
                used.append("cross-patient")
            if pers4 and s in pers4:
                used.append("personalized")
            if pers1 and s in pers1 and not (pers4 and s in pers4):
                used.append("1 h analysis only")
            rows.append([s, r["dataset"], r["role"], f"{float(r['hours']):.1f}", r["seizures"], r["events"],
                         r["eligible"], f"{float(r['interictal_h']):.1f}",
                         ("✓ " + ", ".join(used)) if used else "training only"])
        table_pages(pdf, "CHB-MIT and Siena, patient by patient",
                    ["Patient", "Dataset", "Role", "Hours", "Seizures", "Events", "Eligible", "Interictal h",
                     "Tested in"], rows, [0.13, 0.07, 0.08, 0.06, 0.07, 0.06, 0.07, 0.08, 0.38],
                    note="Green rows were test patients. 'Training only' patients only contributed training data "
                         "(too few eligible seizures or too little interictal EEG to be tested).")
        tusz = by_ds.get("tusz", [])
        if tusz:
            hrs = sum(float(r["hours"]) for r in tusz)
            sz = sum(int(r["seizures"]) for r in tusz)
            el = sum(int(r["eligible"]) for r in tusz)
            table_pages(pdf, "TUSZ, summary", ["Patients", "Role", "Hours", "Seizures", "Eligible events", "Used for"],
                        [[str(len(tusz)), "false_alarm", f"{hrs:.0f}", str(sz), str(el),
                          "✓ false-alarm counting only (never trained on)"]],
                        [0.1, 0.12, 0.1, 0.1, 0.13, 0.45])
        if split:
            rows = []
            for s in sorted(dev + lock):
                group = "development" if s in dev else "lockbox"
                f = feas.get(s, {})
                used = []
                if group == "development":
                    if dry and s in dry:
                        used.append("dry run")
                    if curve and s in curve:
                        used.append("v3 simulation")
                else:
                    if lock_scored and s in lock_scored:
                        used.append("lockbox AUROC")
                    if alarm_subset and s in alarm_subset:
                        used.append("lockbox alarms")
                rows.append([s, group, f.get("eeg_h", "–"), f.get("seizures", "–"), f.get("eligible", "–"),
                             f.get("interictal_h", "–"),
                             ("yes" if f.get("qualifies") else "no") if f else "–",
                             ("✓ " + ", ".join(used)) if used else "not tested"])
            table_pages(pdf, "SeizeIT2, patient by patient",
                        ["Patient", "Group", "EEG h", "Seizures", "Eligible", "Interictal h", "Qualifies",
                         "Tested in"], rows, [0.14, 0.1, 0.07, 0.08, 0.07, 0.09, 0.08, 0.33],
                        note="Seizure counts and qualification come from the development feasibility report; "
                             "lockbox patients' details weren't tabulated per patient (shown as –).")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()

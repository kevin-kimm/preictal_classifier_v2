"""VT-02 to VT-04: harmonization unit tests. See docs/verification_plan.md.

VT-05 (annotation preservation) runs on the real corpus in
scripts/check_harmonization.py; the annotation parsers it relies on are tested
in test_loaders.py.
"""

from pathlib import Path

import numpy as np
import pytest
import yaml

from conftest import write_edf
from preictal.data.edf import read_header
from preictal.data.harmonize import (
    DERIVATIONS, MONTAGE, TARGET_FS, build_montage, expected_length, harmonize,
    microvolt_factor, parse_label, plan_montage, resample,
)

REPO = Path(__file__).resolve().parents[1]
ELECTRODES_OLD = ["Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4", "O1", "O2",
                  "F7", "F8", "T3", "T4", "T5", "T6", "Fz", "Cz", "Pz"]
NEW = {"T3": "T7", "T4": "T8", "T5": "P7", "T6": "P8"}


def test_config_matches_code():
    """configs/default.yaml marks the montage and rate as fixed by the plan; code must agree."""
    cfg = yaml.safe_load((REPO / "configs" / "default.yaml").read_text())
    assert tuple(cfg["signal"]["derivations"]) == DERIVATIONS
    assert cfg["signal"]["target_fs_hz"] == TARGET_FS


# ---------------------------------------------------------------- VT-02

@pytest.mark.parametrize("raw, kind, canonical", [
    # TUH referential labels, old names mapped to new
    ("EEG T3-REF", "electrode", "T7 (ref REF)"),
    ("EEG T4-REF", "electrode", "T8 (ref REF)"),
    ("EEG T5-LE", "electrode", "P7 (ref LE)"),
    ("EEG T6-LE", "electrode", "P8 (ref LE)"),
    ("EEG FP1-REF", "electrode", "Fp1 (ref REF)"),
    ("EEG CZ-LE", "electrode", "Cz (ref LE)"),
    # Siena / mental arithmetic, mixed case
    ("EEG Fp1", "electrode", "Fp1"),
    ("EEG FP2", "electrode", "Fp2"),
    ("EEG Fp2", "electrode", "Fp2"),
    ("EEG T3", "electrode", "T7"),
    ("EEG Fc5", "electrode", "FC5"),
    # CHB-MIT bipolar, referential variants and typos
    ("FP1-F7", "bipolar", "Fp1-F7"),
    ("T7-P7", "bipolar", "T7-P7"),
    ("P7-T7", "bipolar", "P7-T7"),
    ("FZ-CZ", "bipolar", "Fz-Cz"),
    ("FT9-FT10", "bipolar", "FT9-FT10"),
    ("T8-CS2", "electrode", "T8 (ref CS2)"),
    ("FC1-Ref", "electrode", "FC1 (ref REF)"),
    ("T8", "electrode", "T8"),
    ("01", "electrode", "O1"),
    # recognized electrodes outside the montage
    ("EEG T1-REF", "electrode", "T1 (ref REF)"),
    ("EEG C3P-REF", "electrode", "C3P (ref REF)"),
    ("EEG A2-A1", "bipolar", "A2-A1"),
    # non-EEG
    ("ECG ECG", "non_eeg", ""),
    ("EKG EKG", "non_eeg", ""),
    ("ECG EKG-REF", "non_eeg", ""),
    ("EEG EKG1-REF", "non_eeg", ""),
    ("EEG ROC-REF", "non_eeg", ""),
    ("EEG LUC-REF", "non_eeg", ""),
    ("EMG-REF", "non_eeg", ""),
    ("PHOTIC-REF", "non_eeg", ""),
    ("PHOTIC PH", "non_eeg", ""),
    ("RESP ABDOMEN-REF", "non_eeg", ""),
    ("DC1-DC", "non_eeg", ""),
    ("SUPPR", "non_eeg", ""),
    ("SPO2", "non_eeg", ""),
    ("LOC-ROC", "non_eeg", ""),
    ("LUE-RAE", "non_eeg", ""),
    ("VNS", "non_eeg", ""),
    # numbered and placeholder channels
    ("EEG 26-REF", "numbered", ""),
    ("61", "numbered", ""),
    ("1", "numbered", ""),
    ("-", "placeholder", ""),
    (".", "placeholder", ""),
    # unknown
    ("C", "unrecognized", ""),
])
def test_parse_label(raw, kind, canonical):
    lab = parse_label(raw)
    assert lab.kind == kind
    assert lab.canonical == canonical


def test_every_channel_is_logged():
    labels = ["FP1-F7", "F7-T7", "T8-P8", "T8-P8", "-", "ECG", "EEG 26-REF", "C"]
    plan = plan_montage(labels)
    assert [e["raw_label"] for e in plan.channel_log] == labels
    statuses = [e["status"] for e in plan.channel_log]
    assert statuses[:2] == ["used", "used"]
    assert statuses[3] == "excluded: duplicate of an earlier channel"
    assert statuses[4].startswith("excluded: empty placeholder")
    assert statuses[5].startswith("excluded: non-EEG")
    assert statuses[6].startswith("excluded: numbered")
    assert statuses[7] == "unrecognized label"


# ---------------------------------------------------------------- VT-03

@pytest.mark.parametrize("fs_in", [250, 400, 500, 512])
def test_resample_sine(fs_in):
    duration, amp, f0 = 60, 50.0, 10.0
    t = np.arange(duration * fs_in) / fs_in
    y = resample(amp * np.sin(2 * np.pi * f0 * t), fs_in, TARGET_FS)

    assert abs(len(y) - duration * TARGET_FS) <= 1
    assert len(y) == expected_length(len(t), fs_in, TARGET_FS)

    freqs = np.fft.rfftfreq(len(y), 1 / TARGET_FS)
    assert abs(freqs[np.argmax(np.abs(np.fft.rfft(y)))] - f0) <= 0.1

    tt = np.arange(len(y)) / TARGET_FS
    mid = (tt > 5) & (tt < duration - 5)  # avoid filter edge effects
    basis = np.column_stack([np.sin(2 * np.pi * f0 * tt[mid]), np.cos(2 * np.pi * f0 * tt[mid])])
    coef, *_ = np.linalg.lstsq(basis, y[mid], rcond=None)
    assert abs(np.hypot(*coef) - amp) / amp <= 0.01


@pytest.mark.parametrize("unit, factor", [
    ("uV", 1.0), ("\u00b5V", 1.0), ("UV", 1.0), ("mV", 1e3), ("V", 1e6), ("nV", 1e-3), ("", None),
])
def test_microvolt_factor(unit, factor):
    assert microvolt_factor(unit) == factor


def test_millivolt_file_is_converted(tmp_path):
    n = 256 * 4
    fp1, f7 = np.full(n, 30), np.full(n, 10)   # stored as mV
    path = write_edf(tmp_path / "mv.edf", ["EEG Fp1", "EEG F7"], [fp1, f7], 256, units="mV")
    h = harmonize(read_header(path))
    k = DERIVATIONS.index("Fp1-F7")
    assert np.allclose(h.data[k], 20_000.0)    # 20 mV = 20,000 uV


# ---------------------------------------------------------------- VT-04

def referential(rng, n=2048):
    """Random electrode signals in microvolts, keyed by modern name."""
    return {NEW.get(e, e): rng.normal(0, 40, n) for e in ELECTRODES_OLD}


def build_from(labels, arrays):
    plan = plan_montage(labels)
    signals = dict(enumerate(arrays))
    return plan, build_montage(plan, signals, len(arrays[0]))


def test_referential_to_bipolar_exact():
    rng = np.random.default_rng(0)
    x = referential(rng)
    labels = [f"EEG {e.upper()}-REF" for e in ELECTRODES_OLD]
    arrays = [x[NEW.get(e, e)] for e in ELECTRODES_OLD]
    plan, out = build_from(labels, arrays)
    assert plan.present.all()
    for k, (a, b) in enumerate(MONTAGE):
        assert np.max(np.abs(out[k] - (x[a] - x[b]))) <= 1e-6


def test_output_is_reference_independent():
    rng = np.random.default_rng(1)
    x = referential(rng)
    a1, a2 = rng.normal(0, 40, 2048), rng.normal(0, 40, 2048)
    names = [NEW.get(e, e) for e in ELECTRODES_OLD]
    avg = np.mean([x[e] for e in names], axis=0)
    linked_ears = (a1 + a2) / 2

    _, out_avg = build_from([f"EEG {e}-AVG" for e in ELECTRODES_OLD],
                            [x[e] - avg for e in names])
    _, out_le = build_from([f"EEG {e}-LE" for e in ELECTRODES_OLD],
                           [x[e] - linked_ears for e in names])
    _, out_raw = build_from([f"EEG {e}" for e in ELECTRODES_OLD], [x[e] for e in names])
    assert np.max(np.abs(out_avg - out_le)) <= 1e-6
    assert np.max(np.abs(out_avg - out_raw)) <= 1e-6


def test_missing_electrode_is_absent_not_filled():
    rng = np.random.default_rng(2)
    x = referential(rng)
    keep = [e for e in ELECTRODES_OLD if e != "Fz"]
    plan, out = build_from([f"EEG {e}-REF" for e in keep], [x[NEW.get(e, e)] for e in keep])
    k = DERIVATIONS.index("Fz-Cz")
    assert not plan.present[k]
    assert np.isnan(out[k]).all()
    assert "missing Fz" in plan.source(k)
    others = [i for i in range(len(MONTAGE)) if i != k]
    assert plan.present[others].all()
    assert not np.isnan(out[others]).any()


def test_direct_and_reversed_bipolar():
    rng = np.random.default_rng(3)
    s1, s2 = rng.normal(0, 40, 512), rng.normal(0, 40, 512)
    plan, out = build_from(["FP1-F7", "P7-T7"], [s1, s2])
    assert np.array_equal(out[DERIVATIONS.index("Fp1-F7")], s1)
    assert np.array_equal(out[DERIVATIONS.index("T7-P7")], -s2)
    assert plan.source(DERIVATIONS.index("T7-P7")) == "reversed"


def test_mixed_references_are_not_combined():
    plan = plan_montage(["EEG F7-REF", "EEG T3-LE"])
    k = DERIVATIONS.index("F7-T7")
    assert not plan.present[k]
    assert "different references" in plan.source(k)


def test_end_to_end_edf(tmp_path):
    """Referential 512 Hz EDF -> 18 derivations at 256 Hz in microvolts."""
    rng = np.random.default_rng(4)
    n = 512 * 20
    x = {e: np.round(rng.normal(0, 40, n)) for e in ELECTRODES_OLD}
    labels = [f"EEG {e}" for e in ELECTRODES_OLD] + ["ECG ECG", "1"]
    arrays = [x[e] for e in ELECTRODES_OLD] + [np.zeros(n), np.zeros(n)]
    path = write_edf(tmp_path / "siena_like.edf", labels, arrays, 512)
    h = harmonize(read_header(path))
    old = {v: k for k, v in NEW.items()}
    assert h.fs == TARGET_FS and h.present.all()
    assert abs(h.n_samples - 20 * TARGET_FS) <= 1
    for k, (a, b) in enumerate(MONTAGE):
        expected = resample(x[old.get(a, a)] - x[old.get(b, b)], 512, TARGET_FS)
        assert np.max(np.abs(h.data[k] - expected)) <= 1e-6
    statuses = {e["raw_label"]: e["status"] for e in h.channel_log}
    assert statuses["ECG ECG"].startswith("excluded: non-EEG")
    assert statuses["1"].startswith("excluded: numbered")

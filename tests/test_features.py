"""Feature extraction tests (D1 baseline, docs/evaluation_methods.md Section 5)."""

import numpy as np
import pytest
from scipy.signal import welch

from conftest import write_edf
from preictal.data.edf import read_header
from preictal.data.harmonize import DERIVATIONS, harmonize
from preictal.features.build_features import (
    BANDS, CYTON_DERIVATIONS, FEATURES, POOLED_FEATURES, channel_features, pool, recording_features,
)

FS = 256
L = 30 * FS
F = {name: i for i, name in enumerate(FEATURES)}


def sine(freq, amp=50.0, seconds=120, fs=FS):
    t = np.arange(int(seconds * fs)) / fs
    return amp * np.sin(2 * np.pi * freq * t)


def test_config_matches_code():
    from preictal.config import load_config
    cfg = load_config()["features"]
    assert {k: tuple(v) for k, v in cfg["bands_hz"].items()} == BANDS
    assert cfg["welch_segment_s"] == 2 and cfg["spectral_edge_fraction"] == 0.9
    assert tuple(cfg["channel_pooling"]) == ("mean", "std", "min", "max")


def test_feature_lists():
    assert len(FEATURES) == 15 and len(POOLED_FEATURES) == 60
    assert all(d in DERIVATIONS for d in CYTON_DERIVATIONS)


def test_band_power_matches_welch():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 20, 120 * FS)
    starts = np.array([0, 5 * FS, 45 * FS])
    feats = channel_features(x, FS, starts, L)
    for i, s in enumerate(starts):
        f, p = welch(x[s:s + L], fs=FS, nperseg=512, noverlap=256)
        for b, (lo, hi) in BANDS.items():
            expected = p[(f >= lo) & (f < hi)].sum() * (f[1] - f[0])
            assert feats[i, F[f"logpow_{b}"]] == pytest.approx(np.log10(expected), abs=1e-4)


@pytest.mark.parametrize("freq, band", [(2.0, "delta"), (6.0, "theta"), (10.0, "alpha"), (20.0, "beta"), (38.0, "gamma")])
def test_sine_lands_in_its_band(freq, band):
    feats = channel_features(sine(freq), FS, np.array([0]), L)[0]
    assert feats[F[f"relpow_{band}"]] > 0.95
    assert feats[F[f"logpow_{band}"]] == pytest.approx(np.log10(50.0 ** 2 / 2), abs=0.05)


def test_time_domain_features_on_a_sine():
    freq = 10.0
    feats = channel_features(sine(freq), FS, np.array([0]), L)[0]
    assert feats[F["log_variance"]] == pytest.approx(np.log10(50.0 ** 2 / 2), abs=0.01)
    assert feats[F["hjorth_mobility"]] == pytest.approx(2 * np.sin(np.pi * freq / FS), rel=0.01)
    assert feats[F["hjorth_complexity"]] == pytest.approx(1.0, abs=0.02)
    assert 9.5 <= feats[F["sef90"]] <= 11.0


def test_flat_channel_gives_nan_hjorth_not_crash():
    feats = channel_features(np.zeros(60 * FS), FS, np.array([0]), L)[0]
    assert np.isnan(feats[F["hjorth_mobility"]]) and np.isnan(feats[F["sef90"]])


def test_pool_ignores_absent_channels_and_count():
    rng = np.random.default_rng(1)
    per = rng.normal(size=(4, 18, 15)).astype(np.float32)
    per_missing = per.copy()
    per_missing[:, 5, :] = np.nan
    pooled = pool(per_missing)
    assert pooled.shape == (4, 60)
    keep = [k for k in range(18) if k != 5]
    assert np.allclose(pooled, pool(per, channels=keep), equal_nan=True)


def test_pool_order_matches_names():
    per = np.zeros((1, 18, 15), dtype=np.float32)
    per[0, :, F["sef90"]] = np.arange(18)
    pooled = pool(per)[0]
    assert pooled[POOLED_FEATURES.index("max_sef90")] == 17
    assert pooled[POOLED_FEATURES.index("min_sef90")] == 0


def _siena_like_edf(tmp_path, seconds=200):
    rng = np.random.default_rng(2)
    names = ["Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4", "O1", "O2",
             "F7", "F8", "T3", "T4", "T5", "T6", "Fz", "Cz", "Pz"]
    sigs = [np.round(rng.normal(0, 30, 512 * seconds)) for _ in names]
    return write_edf(tmp_path / "x.edf", [f"EEG {n}" for n in names], sigs, 512)


def test_harmonized_piece_matches_whole(tmp_path):
    hdr = read_header(_siena_like_edf(tmp_path))
    whole = harmonize(hdr)
    piece = harmonize(hdr, start_s=50, stop_s=110)
    assert piece.t0 == 50
    a = int(50 * FS)
    assert np.max(np.abs(piece.data - whole.data[:, a:a + piece.n_samples])) < 1e-6


def test_features_do_not_depend_on_chunking(tmp_path):
    hdr = read_header(_siena_like_edf(tmp_path))
    starts = np.arange(0, 200 - 30 + 1e-9, 5.0)
    one, present = recording_features(hdr, starts, 30, chunk_windows=10_000)
    many, _ = recording_features(hdr, starts, 30, chunk_windows=7)
    assert present.all()
    assert np.allclose(one, many, rtol=1e-4, atol=1e-4, equal_nan=True)
    assert not np.isnan(one).any()

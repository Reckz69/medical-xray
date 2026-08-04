"""Unit tests for worker.preprocess (Stage 3.2 gate)."""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from worker.preprocess import iter_tiles, noise_detection, pad_to_tile


def _ramp(h: int = 300, w: int = 400) -> np.ndarray:
    row = np.linspace(0, 255, w, dtype=np.float64)
    return np.tile(row, (h, 1)).astype(np.uint8)


def test_noise_detection_constant_image_is_zero() -> None:
    img = np.full((128, 128), 128, dtype=np.uint8)
    assert noise_detection(img) == 0.0


def test_noise_detection_smooth_ramp_is_low() -> None:
    assert noise_detection(_ramp()) < 1.0


def test_noise_detection_noisy_image_is_high() -> None:
    """Gaussian noise on a flat image (no edges) must register high variance."""
    rng = np.random.default_rng(42)
    base = np.full((128, 128), 128, dtype=np.float64)
    noisy = np.clip(base + rng.normal(0, 30, (128, 128)), 0, 255).astype(np.uint8)
    assert noise_detection(noisy) > 5.0


def test_noise_detection_matches_legacy_oracle() -> None:
    import inference_engine as legacy

    rng = np.random.default_rng(7)
    for _ in range(3):
        img = rng.integers(0, 256, (90, 130), dtype=np.uint8)
        assert noise_detection(img) == pytest.approx(
            legacy._detect_noise_level(img), abs=0.0
        )


def test_noise_detection_matches_legacy_on_real_images() -> None:
    import inference_engine as legacy

    root = pathlib.Path(__file__).resolve().parents[2]
    for rel, name in [
        ("Images/dataset_x-ray1.png", "scan.png"),
        ("Images/high_noise_dicom.dicom", "scan.dcm"),
        ("Images/low_nosie_dicom.dicom", "scan.dcm"),
    ]:
        path = root / rel
        if not path.exists():
            continue
        img = legacy._load_image_from_bytes(path.read_bytes(), name)
        assert noise_detection(img) == pytest.approx(
            legacy._detect_noise_level(img), abs=1e-6
        ), rel


def test_pad_to_tile_exact_multiple_unchanged() -> None:
    img = _ramp(256, 256)
    padded = pad_to_tile(img)
    assert padded.shape == (256, 256)


def test_pad_to_tile_pads_to_multiple() -> None:
    img = _ramp(300, 400)
    padded = pad_to_tile(img)
    assert padded.shape == (512, 512)
    assert img[0, 0] == padded[0, 0]
    assert np.array_equal(padded[:300, :400], img)


def test_pad_to_tile_reflect_mode() -> None:
    img = _ramp(10, 12)
    padded = pad_to_tile(img)
    assert padded.shape == (256, 256)
    assert np.array_equal(padded[:10, :12], img)


def test_iter_tiles_covers_whole_padded_image() -> None:
    padded = pad_to_tile(_ramp(300, 400))
    tiles = list(iter_tiles(padded))
    assert len(tiles) == 4  # 2x2
    area = 0
    for i, j, patch in tiles:
        assert patch.shape == (256, 256)
        area += patch.size
    assert area == padded.size


def test_iter_tiles_normalizes_to_unit_range() -> None:
    padded = pad_to_tile(_ramp(100, 100))
    _, _, patch = next(iter_tiles(padded))
    assert patch.dtype == np.float64
    assert patch.min() >= 0.0
    assert patch.max() <= 1.0


def test_iter_tiles_matches_legacy_tile_norm() -> None:
    img = _ramp(300, 400)
    padded = pad_to_tile(img)
    for i, j, patch in iter_tiles(padded):
        legacy_patch = padded[i : i + 256, j : j + 256] / 255.0
        np.testing.assert_array_equal(patch, legacy_patch)

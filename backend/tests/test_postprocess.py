"""Unit tests for worker.postprocess (Stage 3.5)."""

from __future__ import annotations

import pathlib

import cv2
import numpy as np

from worker.postprocess import encode_png, enhance


def _ramp(h: int = 128, w: int = 200) -> np.ndarray:
    row = np.linspace(0, 255, w, dtype=np.float64)
    return np.tile(row, (h, 1)).astype(np.uint8)


def test_enhance_matches_legacy_clinical_enhance() -> None:
    import inference_engine as legacy

    rng = np.random.default_rng(3)
    for _ in range(3):
        img = rng.integers(0, 256, (96, 128), dtype=np.uint8)
        np.testing.assert_array_equal(enhance(img), legacy._clinical_enhance(img))


def test_enhance_matches_legacy_on_real_image() -> None:
    import inference_engine as legacy

    root = pathlib.Path(__file__).resolve().parents[2]
    path = root / "Images" / "dataset_x-ray1.png"
    img = legacy._load_image_from_bytes(path.read_bytes(), "scan.png")
    np.testing.assert_array_equal(enhance(img), legacy._clinical_enhance(img))


def test_enhance_returns_same_shape_and_dtype() -> None:
    img = _ramp()
    out = enhance(img)
    assert out.shape == img.shape
    assert out.dtype == np.uint8


def test_encode_png_emits_png_bytes() -> None:
    img = _ramp()
    data = encode_png(img)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    decoded = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    assert decoded.shape == img.shape
    np.testing.assert_allclose(decoded, img, atol=1)


def test_encode_png_matches_legacy_to_b64_png_body() -> None:
    import base64

    import inference_engine as legacy

    img = _ramp()
    legacy_uri = legacy._to_b64_png(img)
    legacy_body = base64.b64decode(legacy_uri.split(",", 1)[1])
    np.testing.assert_array_equal(encode_png(img), legacy_body)

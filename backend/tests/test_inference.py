"""Inference tests (Stage 3.4 gate).

Unit test exercises the tile/stitch/reconstruct path with a fake identity
model (no TensorFlow). The real-model test compares the ported output against
the frozen legacy ``_run_unet`` and is skipped when weights are unavailable.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from worker.inference import denoise
from worker.model_manager import ModelManager

_WEIGHTS = pathlib.Path(__file__).resolve().parents[2] / "n2n_unet_best_weights04.keras"


class IdentityModel:
    def predict(self, x, verbose=0):
        return x


def _ramp(h: int = 300, w: int = 400) -> np.ndarray:
    row = np.linspace(0, 255, w, dtype=np.float64)
    return np.tile(row, (h, 1)).astype(np.uint8)


async def test_denoise_identity_reconstructs_image() -> None:
    img = _ramp()
    out = await denoise(IdentityModel(), img)
    assert out.unet.shape == img.shape
    assert out.unet.dtype == np.uint8
    np.testing.assert_allclose(out.unet, img, atol=1)


async def test_denoise_identity_noise_map_is_zero() -> None:
    img = _ramp()
    out = await denoise(IdentityModel(), img)
    assert out.noise_map.shape == img.shape
    assert np.count_nonzero(out.noise_map) == 0


async def test_denoise_pads_non_multiple_dimensions() -> None:
    img = _ramp(h=300, w=400)
    out = await denoise(IdentityModel(), img)
    assert out.unet.shape == (300, 400)


async def test_denoise_small_image() -> None:
    img = _ramp(h=64, w=64)
    out = await denoise(IdentityModel(), img)
    assert out.unet.shape == (64, 64)


@pytest.mark.skipif(not _WEIGHTS.exists(), reason="model weights not present")
async def test_denoise_matches_legacy_run_unet() -> None:
    """Cross-check the ported tiled inference against the legacy oracle."""
    import inference_engine as legacy

    manager = ModelManager()
    manager.startup()
    model = manager.get_pipeline()

    data = pathlib.Path(_WEIGHTS).resolve().parent / "Images" / "dataset_x-ray1.png"
    img = legacy._load_image_from_bytes(data.read_bytes(), "scan.png")

    out = await denoise(model, img)
    legacy_unet, legacy_noise = legacy._run_unet(img, model)

    np.testing.assert_array_equal(out.unet, legacy_unet)
    np.testing.assert_array_equal(out.noise_map, legacy_noise)

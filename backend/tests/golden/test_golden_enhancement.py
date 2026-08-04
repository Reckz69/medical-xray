"""Golden regression gates (Stage 3.5).

Run the new pipeline and the frozen legacy oracle on the same real X-ray
fixtures and assert the four encoded outputs stay within the quality gates:
``psnr > 35`` AND ``ssim > 0.95`` (scikit-image). The new pipeline is a
faithful port, so today these are effectively identical; the gates exist to
catch future drift.

Run explicitly with: ``pytest -m golden``
"""

from __future__ import annotations

import asyncio
import pathlib

import numpy as np
import pytest
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

from worker.converters import CommonImage
from worker.inference import denoise
from worker.model_manager import ModelManager
from worker.postprocess import encode_png, enhance
from worker.preprocess import noise_detection

_WEIGHTS = pathlib.Path(__file__).resolve().parents[3] / "n2n_unet_best_weights04 (2).keras"

pytestmark = [
    pytest.mark.golden,
    pytest.mark.skipif(not _WEIGHTS.exists(), reason="model weights not present"),
]

_FIXTURES = [
    ("Images/high_noise_dicom.dicom", "scan.dcm"),
    ("Images/low_nosie_dicom.dicom", "scan.dcm"),
    ("Images/dataset_x-ray1.png", "scan.png"),
]


def _legacy_pipeline(data: bytes, name: str, model) -> list[bytes]:
    import inference_engine as legacy

    raw = legacy._load_image_from_bytes(data, name)
    noise_variance = legacy._detect_noise_level(raw)
    if noise_variance > 8.0:
        unet, noise_map = legacy._run_unet(raw, model)
    else:
        unet = raw.copy()
        noise_map = np.zeros_like(raw)
    enhanced = legacy._clinical_enhance(unet)
    return [
        legacy._to_b64_png(raw).encode("ascii"),
        legacy._to_b64_png(noise_map).encode("ascii"),
        legacy._to_b64_png(unet).encode("ascii"),
        legacy._to_b64_png(enhanced).encode("ascii"),
    ]


async def _new_pipeline(data: bytes, name: str, model) -> list[bytes]:
    import base64

    img = CommonImage.from_bytes(data, name).data
    noise_variance = noise_detection(img)
    if noise_variance > 8.0:
        out = await denoise(model, img)
        unet, noise_map = out.unet, out.noise_map
    else:
        unet = img.copy()
        noise_map = np.zeros_like(img)
    enhanced = enhance(unet)
    raw_bytes = encode_png(img)
    return [
        b"data:image/png;base64," + base64.b64encode(raw_bytes),
        _b64(encode_png(noise_map)),
        _b64(encode_png(unet)),
        _b64(encode_png(enhanced)),
    ]


def _b64(png: bytes) -> bytes:
    import base64

    return b"data:image/png;base64," + base64.b64encode(png)


def _decode_png(png_bytes: bytes) -> np.ndarray:
    import base64

    import cv2

    body = png_bytes.split(b",", 1)[1] if b"," in png_bytes else png_bytes
    buf = np.frombuffer(base64.b64decode(body), dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)


async def _run_golden(rel: str, name: str) -> None:
    root = pathlib.Path(_WEIGHTS).resolve().parent
    data = (root / rel).read_bytes()

    manager = ModelManager()
    manager.startup()
    model = manager.get_pipeline()

    legacy_outs = _legacy_pipeline(data, name, model)
    new_outs = await _new_pipeline(data, name, model)

    assert len(new_outs) == len(legacy_outs) == 4
    for idx, label in enumerate(["original", "noise_map", "unet", "enhanced"]):
        ref = _decode_png(legacy_outs[idx])
        out = _decode_png(new_outs[idx])
        assert out.shape == ref.shape, label
        psnr = peak_signal_noise_ratio(ref, out)
        ssim = structural_similarity(ref, out, data_range=255)
        assert psnr > 35, f"{label}: psnr {psnr:.2f} <= 35"
        assert ssim > 0.95, f"{label}: ssim {ssim:.4f} <= 0.95"


@pytest.mark.parametrize("rel,name", _FIXTURES)
def test_golden_pipeline_quality(rel: str, name: str) -> None:
    asyncio.run(_run_golden(rel, name))

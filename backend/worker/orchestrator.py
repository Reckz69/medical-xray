"""Pipeline orchestration (ADR-008).

``run`` coordinates the staged modules — conversion (CommonImage),
preprocessing (tiling + Canny noise variance), routing, inference (tiled
threaded U-Net predict), postprocessing (CLAHE + unsharp mask), and encoding
— into a single ``PipelineResult`` with the four PNG outputs plus routing
metadata and per-stage timings. It is the seam the executor calls; the
executor stays persistence/transport-only.

Faithful port of the frozen legacy ``inference_engine.run_pipeline``.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import numpy as np

from gateway.core.config import settings
from worker.converters import CommonImage
from worker.inference import denoise
from worker.postprocess import encode_png, enhance
from worker.preprocess import noise_detection


@dataclass(frozen=True)
class StageTimings:
    """Per-stage wall-clock times in milliseconds."""

    conversion_ms: float
    preprocessing_ms: float
    inference_ms: float
    postprocessing_ms: float
    encode_ms: float
    total_ms: float

    def as_dict(self) -> dict[str, float]:
        return {
            "conversion_ms": self.conversion_ms,
            "preprocessing_ms": self.preprocessing_ms,
            "inference_ms": self.inference_ms,
            "postprocessing_ms": self.postprocessing_ms,
            "encode_ms": self.encode_ms,
            "total_ms": self.total_ms,
        }


@dataclass(frozen=True)
class PipelineResult:
    """The four encoded PNG outputs plus routing metadata."""

    original_png: bytes
    noise_map_png: bytes
    unet_png: bytes
    enhanced_png: bytes
    routing_message: str
    noise_variance: float
    was_bypassed: bool
    width: int
    height: int
    fmt: str
    timings: StageTimings


async def run(
    data: bytes,
    *,
    fmt: str,
    model_manager,
    original_name: str = "",
    noise_threshold: float | None = None,
    tile: int | None = None,
) -> PipelineResult:
    """Run the full denoising pipeline on raw image bytes."""
    threshold = noise_threshold if noise_threshold is not None else settings.noise_threshold
    tile_size = tile if tile is not None else settings.model_tile
    started = time.perf_counter()

    # 1. Conversion
    t = time.perf_counter()
    common = CommonImage.from_bytes(data, original_name)
    img = common.data
    conversion_ms = (time.perf_counter() - t) * 1000

    # 2. Preprocessing (smart gateway)
    t = time.perf_counter()
    noise_variance = noise_detection(img)
    preprocessing_ms = (time.perf_counter() - t) * 1000

    # 3. Routing + inference
    t = time.perf_counter()
    model = await asyncio.to_thread(model_manager.get_pipeline)
    if noise_variance > threshold:
        routing_message = (
            f"PATH A: Heavy scatter detected "
            f"(Var: {noise_variance:.1f}). AI Denoising Engaged."
        )
        was_bypassed = False
        out = await denoise(model, img, tile=tile_size)
        unet, noise_map = out.unet, out.noise_map
    else:
        routing_message = (
            f"PATH B: Clean digital scan detected "
            f"(Var: {noise_variance:.1f}). AI Bypassed to preserve bones."
        )
        was_bypassed = True
        unet = img.copy()
        noise_map = np.zeros_like(img)
    inference_ms = (time.perf_counter() - t) * 1000

    # 4. Postprocessing (deterministic clinical enhancement)
    t = time.perf_counter()
    enhanced = enhance(unet)
    postprocessing_ms = (time.perf_counter() - t) * 1000

    # 5. Encode outputs
    t = time.perf_counter()
    original_png = encode_png(img)
    noise_map_png = encode_png(noise_map)
    unet_png = encode_png(unet)
    enhanced_png = encode_png(enhanced)
    encode_ms = (time.perf_counter() - t) * 1000

    total_ms = (time.perf_counter() - started) * 1000
    timings = StageTimings(
        conversion_ms=conversion_ms,
        preprocessing_ms=preprocessing_ms,
        inference_ms=inference_ms,
        postprocessing_ms=postprocessing_ms,
        encode_ms=encode_ms,
        total_ms=total_ms,
    )

    return PipelineResult(
        original_png=original_png,
        noise_map_png=noise_map_png,
        unet_png=unet_png,
        enhanced_png=enhanced_png,
        routing_message=routing_message,
        noise_variance=noise_variance,
        was_bypassed=was_bypassed,
        width=common.width,
        height=common.height,
        fmt=fmt,
        timings=timings,
    )


__all__ = ["PipelineResult", "StageTimings", "run"]

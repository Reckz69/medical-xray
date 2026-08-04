"""Inference — tiled U-Net predict run in a worker thread (Stage 3.4).

Faithful port of the legacy ``inference_engine._run_unet``: reflect-pad to
whole tiles, predict each 256x256 patch, stitch, crop, and build the noise
residual visualization. The full tiled run is offloaded with
``asyncio.to_thread`` so the worker event loop is never blocked.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import cv2
import numpy as np

from worker.preprocess import DEFAULT_TILE, iter_tiles, pad_to_tile


@dataclass(frozen=True)
class DenoiseOutput:
    """Result of a tiled denoising run."""

    unet: np.ndarray  # uint8 grayscale denoised image
    noise_map: np.ndarray  # uint8 grayscale residual visualization


def _denoise_sync(model, img: np.ndarray, tile: int = DEFAULT_TILE) -> DenoiseOutput:
    """Run the legacy tile loop synchronously (mirrors ``_run_unet``)."""
    h, w = img.shape
    padded = pad_to_tile(img, tile)

    denoised_padded = np.zeros_like(padded, dtype=np.float32)
    for i, j, patch in iter_tiles(padded, tile):
        patch_input = np.expand_dims(patch, axis=(0, -1))
        prediction = model.predict(patch_input, verbose=0)[0, :, :, 0]
        denoised_padded[i : i + tile, j : j + tile] = prediction

    denoised_float = denoised_padded[:h, :w]
    unet_output = np.clip(denoised_float * 255.0, 0, 255).astype(np.uint8)

    residual_map = cv2.absdiff(img, unet_output)
    _, pure_noise = cv2.threshold(residual_map, 4, 255, cv2.THRESH_TOZERO)
    residual_visual = np.clip(pure_noise * 4, 0, 255).astype(np.uint8)

    return DenoiseOutput(unet=unet_output, noise_map=residual_visual)


async def denoise(
    model, img: np.ndarray, *, tile: int = DEFAULT_TILE
) -> DenoiseOutput:
    """Tiled denoising offloaded to a thread so the event loop stays free."""
    return await asyncio.to_thread(_denoise_sync, model, img, tile)


__all__ = ["DenoiseOutput", "denoise"]

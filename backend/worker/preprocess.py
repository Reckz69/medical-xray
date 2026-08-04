"""Preprocessing — flat-tissue noise variance and image tiling (Stage 3.2).

Faithful port of the frozen legacy ``inference_engine._detect_noise_level``
and the tiling helpers inside ``_run_unet``. Must stay equivalent to the
legacy oracle until it is decommissioned.
"""

from __future__ import annotations

from collections.abc import Iterator

import cv2
import numpy as np

DEFAULT_TILE = 256


def noise_detection(image_array: np.ndarray) -> float:
    """Noise variance in flat tissue, ignoring bone edges.

    Mirrors ``inference_engine._detect_noise_level`` exactly: Canny 50/150,
    5x5 dilation, median blur 5, then the variance of the static residual
    over non-edge pixels.
    """
    edges = cv2.Canny(image_array, 50, 150)
    kernel = np.ones((5, 5), np.uint8)
    edge_mask = cv2.dilate(edges, kernel, iterations=1)
    flat_areas_mask = cv2.bitwise_not(edge_mask)

    blurred = cv2.medianBlur(image_array, 5)
    static_residual = cv2.absdiff(image_array, blurred)
    flat_noise = static_residual[flat_areas_mask == 255]

    if len(flat_noise) == 0:
        return 0.0

    return float(np.var(flat_noise))


def pad_to_tile(img: np.ndarray, tile: int = DEFAULT_TILE) -> np.ndarray:
    """Pad ``img`` reflectively to whole tiles, like the legacy ``_run_unet``."""
    h, w = img.shape
    pad_h = (tile - h % tile) % tile
    pad_w = (tile - w % tile) % tile
    return np.pad(img, ((0, pad_h), (0, pad_w)), mode="reflect")


def iter_tiles(
    padded: np.ndarray, tile: int = DEFAULT_TILE
) -> Iterator[tuple[int, int, np.ndarray]]:
    """Yield ``(row, col, patch)`` for each tile of a padded image.

    Patches are normalized to [0, 1] the same way the legacy loop did
    (``patch / 255.0``) so inference consumes a ready-made model input.
    """
    for i in range(0, padded.shape[0], tile):
        for j in range(0, padded.shape[1], tile):
            patch = padded[i : i + tile, j : j + tile] / 255.0
            yield i, j, patch


__all__ = ["DEFAULT_TILE", "iter_tiles", "noise_detection", "pad_to_tile"]

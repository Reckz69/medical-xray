"""Postprocessing — clinical enhancement and PNG encoding (Stage 3.5).

Faithful port of the frozen legacy ``inference_engine._clinical_enhance``
(CLAHE + unsharp masking) and a byte-level PNG encoder. The worker persists
raw PNG bytes (no ``data:`` URI prefix — that is a legacy API concern).
"""

from __future__ import annotations

import cv2
import numpy as np


def enhance(img: np.ndarray) -> np.ndarray:
    """Deterministic clinical enhancement: CLAHE then unsharp masking.

    Mirrors ``inference_engine._clinical_enhance`` exactly:
    ``createCLAHE(clipLimit=1.0, tileGridSize=(8,8))`` → GaussianBlur (5,5,1.0)
    → ``addWeighted(contrast_enhanced, 1.1, smoothed, -0.2, 0)``.
    """
    clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(8, 8))
    contrast_enhanced = clahe.apply(img)
    smoothed = cv2.GaussianBlur(contrast_enhanced, (5, 5), 1.0)
    return cv2.addWeighted(contrast_enhanced, 1.1, smoothed, -0.2, 0)


def encode_png(img: np.ndarray) -> bytes:
    """Encode a uint8 grayscale array to PNG bytes."""
    success, buf = cv2.imencode(".png", img)
    if not success:
        raise RuntimeError("Failed to encode image to PNG")
    return buf.tobytes()


__all__ = ["encode_png", "enhance"]

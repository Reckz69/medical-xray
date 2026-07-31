"""
inference_engine.py
--------------------
Core ML inference engine for Denoise X.
Adapted from the original inference.py — the model file is NOT modified.
Exposes a single entry-point: run_pipeline(image_bytes, filename) → DenoiseResult
"""

import io
import base64
import logging
import os
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image as PILImage

logger = logging.getLogger("denoise_x.engine")

# ── lazy-loaded globals ────────────────────────────────────────────────────────
_model = None
_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "n2n_unet_best_weights04 (2).keras"
)


def _load_model():
    """Load the Keras model once, on first request."""
    global _model
    if _model is None:
        import tensorflow as tf  # deferred import keeps startup fast

        logger.info("Loading N2N U-Net model from: %s", _MODEL_PATH)
        _model = tf.keras.models.load_model(_MODEL_PATH, compile=False)
        logger.info("Model loaded successfully.")
    return _model


# ── result dataclass ───────────────────────────────────────────────────────────
@dataclass
class DenoiseResult:
    original_b64: str          # Base64-encoded PNG of the raw input
    noise_map_b64: str         # Base64-encoded PNG of the noise residual map
    unet_b64: str              # Base64-encoded PNG of the raw U-Net output
    enhanced_b64: str          # Base64-encoded PNG of the final clinical output
    routing_message: str       # Human-readable routing decision
    noise_variance: float      # Calculated flat-tissue noise variance
    was_bypassed: bool         # True if the AI was skipped (clean scan)
    width: int                 # Original image width (px)
    height: int                # Original image height (px)


# ── helper: ndarray → base64 PNG ──────────────────────────────────────────────
def _to_b64_png(img_array: np.ndarray) -> str:
    """Convert a uint8 grayscale ndarray to a base64-encoded PNG data URI."""
    success, buf = cv2.imencode(".png", img_array)
    if not success:
        raise RuntimeError("Failed to encode image to PNG")
    b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


# ── helper: load image from raw bytes ─────────────────────────────────────────
def _load_image_from_bytes(image_bytes: bytes, filename: str) -> np.ndarray:
    """
    Read image bytes into a uint8 grayscale numpy array.
    Supports: PNG, JPEG, and DICOM (.dcm / .dicom).
    """
    lower = filename.lower()

    if lower.endswith(".dcm") or lower.endswith(".dicom"):
        import pydicom

        dicom_data = pydicom.dcmread(io.BytesIO(image_bytes))
        pixel_array = dicom_data.pixel_array.astype(float)
        pixel_array = (np.maximum(pixel_array, 0) / pixel_array.max()) * 255.0
        raw_img = np.uint8(pixel_array)

        if (
            hasattr(dicom_data, "PhotometricInterpretation")
            and dicom_data.PhotometricInterpretation == "MONOCHROME1"
        ):
            raw_img = cv2.bitwise_not(raw_img)

    else:
        # PNG / JPEG via PIL → ensures consistent grayscale decoding
        pil_img = PILImage.open(io.BytesIO(image_bytes)).convert("L")
        raw_img = np.array(pil_img, dtype=np.uint8)

    if raw_img is None or raw_img.size == 0:
        raise ValueError("Image could not be loaded. Check the file format.")

    return raw_img


# ── Smart Gateway: noise variance in flat tissue ───────────────────────────────
def _detect_noise_level(image_array: np.ndarray) -> float:
    """
    Calculates noise variance ONLY in the flat tissue, ignoring bone edges.
    Identical logic to the original inference.py — not changed.
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


# ── U-Net patch-based denoising ───────────────────────────────────────────────
def _run_unet(raw_img: np.ndarray, ai_model) -> tuple[np.ndarray, np.ndarray]:
    """
    Tile the image into 256×256 patches, run U-Net, stitch back.
    Returns (unet_output_uint8, residual_visual_uint8).
    """
    h, w = raw_img.shape

    pad_h = (256 - h % 256) % 256
    pad_w = (256 - w % 256) % 256
    padded_img = np.pad(raw_img, ((0, pad_h), (0, pad_w)), mode="reflect")
    new_h, new_w = padded_img.shape

    denoised_padded = np.zeros_like(padded_img, dtype=np.float32)

    for i in range(0, new_h, 256):
        for j in range(0, new_w, 256):
            patch = padded_img[i : i + 256, j : j + 256] / 255.0
            patch_input = np.expand_dims(patch, axis=(0, -1))
            prediction = ai_model.predict(patch_input, verbose=0)[0, :, :, 0]
            denoised_padded[i : i + 256, j : j + 256] = prediction

    denoised_float = denoised_padded[:h, :w]
    unet_output = np.clip(denoised_float * 255.0, 0, 255).astype(np.uint8)

    residual_map = cv2.absdiff(raw_img, unet_output)
    _, pure_noise = cv2.threshold(residual_map, 4, 255, cv2.THRESH_TOZERO)
    residual_visual = np.clip(pure_noise * 4, 0, 255).astype(np.uint8)

    return unet_output, residual_visual


# ── CLAHE + unsharp masking (deterministic post-processing) ───────────────────
def _clinical_enhance(img: np.ndarray) -> np.ndarray:
    """
    Deterministic OpenCV enhancement — mirrors inference.py exactly.
    Applied to BOTH paths (AI denoised AND clean-bypass).

    NOTE: No additional contrast manipulation is added here beyond what
    inference.py defines. Any change to inference.py must be reflected
    exactly in this function.
    """
    clahe = cv2.createCLAHE(clipLimit=1.0, tileGridSize=(8, 8))
    contrast_enhanced = clahe.apply(img)
    smoothed = cv2.GaussianBlur(contrast_enhanced, (5, 5), 1.0)
    # Synced with inference.py line 114: addWeighted(contrast_enhanced, 1.1, smoothed, -0.2, 0)
    final_output = cv2.addWeighted(contrast_enhanced, 1.1, smoothed, -0.2, 0)
    return final_output


# ── Master public entry-point ──────────────────────────────────────────────────
def run_pipeline(
    image_bytes: bytes,
    filename: str,
    noise_threshold: float = 8.0,
) -> DenoiseResult:
    """
    Execute the full Denoise X pipeline on raw image bytes.

    Parameters
    ----------
    image_bytes : bytes      Raw file bytes from the upload
    filename    : str        Original filename (used to detect DICOM)
    noise_threshold : float  Gateway threshold (default 8.0, matching inference.py)

    Returns
    -------
    DenoiseResult  dataclass with base64-encoded PNGs and metadata
    """
    logger.info("Pipeline start — file: %s", filename)

    # 1. Load image
    raw_img = _load_image_from_bytes(image_bytes, filename)
    h, w = raw_img.shape
    logger.info("Image loaded — shape: %dx%d", h, w)

    # 2. Smart Gateway
    noise_variance = _detect_noise_level(raw_img)
    logger.info("Noise variance: %.4f (threshold: %.1f)", noise_variance, noise_threshold)

    if noise_variance > noise_threshold:
        routing_message = (
            f"PATH A: Heavy scatter detected "
            f"(Var: {noise_variance:.1f}). AI Denoising Engaged."
        )
        was_bypassed = False
        logger.info("Routing → PATH A (AI denoising)")

        model = _load_model()
        unet_output, residual_visual = _run_unet(raw_img, model)

    else:
        routing_message = (
            f"PATH B: Clean digital scan detected "
            f"(Var: {noise_variance:.1f}). AI Bypassed to preserve bones."
        )
        was_bypassed = True
        logger.info("Routing → PATH B (bypass)")

        unet_output = raw_img.copy()
        residual_visual = np.zeros_like(raw_img)

    # 3. Deterministic clinical enhancement (both paths)
    logger.info("Applying clinical enhancement (CLAHE + USM)")
    final_output = _clinical_enhance(unet_output)

    logger.info("Pipeline complete — encoding results")

    return DenoiseResult(
        original_b64=_to_b64_png(raw_img),
        noise_map_b64=_to_b64_png(residual_visual),
        unet_b64=_to_b64_png(unet_output),
        enhanced_b64=_to_b64_png(final_output),
        routing_message=routing_message,
        noise_variance=noise_variance,
        was_bypassed=was_bypassed,
        width=w,
        height=h,
    )

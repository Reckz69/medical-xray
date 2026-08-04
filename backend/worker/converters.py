"""Image conversion — CommonImage (ADR-007).

Turns raw upload bytes into a normalized grayscale ``uint8`` array with the
detected format recorded, so downstream stages (preprocessing, inference,
postprocessing) never re-detect or re-decode. Pure converter: no TensorFlow
import.

The decoding logic is a faithful port of the frozen legacy
``inference_engine._load_image_from_bytes`` and must stay equivalent to it
until the legacy module is decommissioned.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image as PILImage

from gateway.models.scan import FORMAT_DICOM, FORMAT_JPEG, FORMAT_PNG

_DICOM_EXTENSIONS = (".dcm", ".dicom")
_JPEG_EXTENSIONS = (".jpg", ".jpeg")


def _format_from_filename(filename: str) -> str | None:
    lower = filename.lower()
    if lower.endswith(_DICOM_EXTENSIONS):
        return FORMAT_DICOM
    if lower.endswith(_JPEG_EXTENSIONS):
        return FORMAT_JPEG
    if lower.endswith(".png"):
        return FORMAT_PNG
    return None


def _decode_dicom(data: bytes) -> np.ndarray:
    """Decode DICOM bytes to a uint8 grayscale array (MONOCHROME1 inverted)."""
    import pydicom

    dicom_data = pydicom.dcmread(io.BytesIO(data))
    pixel_array = dicom_data.pixel_array.astype(float)
    pixel_array = (np.maximum(pixel_array, 0) / pixel_array.max()) * 255.0
    raw_img = np.uint8(pixel_array)
    if (
        hasattr(dicom_data, "PhotometricInterpretation")
        and dicom_data.PhotometricInterpretation == "MONOCHROME1"
    ):
        raw_img = cv2.bitwise_not(raw_img)
    return raw_img


def _decode_raster(data: bytes) -> np.ndarray:
    """Decode PNG/JPEG bytes to a uint8 grayscale array."""
    pil_img = PILImage.open(io.BytesIO(data)).convert("L")
    return np.array(pil_img, dtype=np.uint8)


@dataclass(frozen=True)
class CommonImage:
    """A decoded image: grayscale uint8 array plus its detected format."""

    data: np.ndarray
    fmt: str
    original_name: str

    @property
    def shape(self) -> tuple[int, int]:
        return self.data.shape

    @property
    def width(self) -> int:
        return self.data.shape[1]

    @property
    def height(self) -> int:
        return self.data.shape[0]

    @classmethod
    def from_bytes(cls, data: bytes, filename: str) -> CommonImage:
        """Decode raw bytes into a CommonImage (mirrors legacy loader)."""
        fmt = _format_from_filename(filename)
        if fmt is None:
            raise ValueError(
                f"Unsupported file type for {filename!r}. "
                "Allowed: .png, .jpg, .jpeg, .dcm, .dicom"
            )
        if fmt == FORMAT_DICOM:
            raw_img = _decode_dicom(data)
        else:
            raw_img = _decode_raster(data)
        if raw_img is None or raw_img.size == 0:
            raise ValueError("Image could not be loaded. Check the file format.")
        return cls(data=raw_img, fmt=fmt, original_name=filename)


__all__ = ["CommonImage"]

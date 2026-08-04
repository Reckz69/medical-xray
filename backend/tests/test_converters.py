"""Unit tests for worker.converters.CommonImage (Stage 3.1 gate)."""

from __future__ import annotations

import io

import cv2
import numpy as np
import pydicom
import pytest
from PIL import Image
from pydicom.uid import ExplicitVRLittleEndian

from gateway.models.scan import FORMAT_DICOM, FORMAT_JPEG, FORMAT_PNG
from worker.converters import CommonImage


def _png_bytes(gray: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(gray, mode="L").save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(gray: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(gray, mode="L").save(buf, format="JPEG")
    return buf.getvalue()


def _dicom_bytes(
    pixel_array: np.ndarray,
    photometric: str = "MONOCHROME2",
) -> bytes:
    ds = pydicom.dataset.Dataset()
    ds.file_meta = pydicom.dataset.FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = pydicom.uid.CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID = pydicom.uid.CTImageStorage
    ds.SOPInstanceUID = pydicom.uid.generate_uid()
    ds.PatientName = "Test^Patient"
    ds.Modality = "CT"
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = photometric
    ds.Rows, ds.Columns = pixel_array.shape
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PixelData = pixel_array.astype(np.uint16).tobytes()

    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=True, little_endian=True, implicit_vr=False)
    return buf.getvalue()


def _ramp_gray(h: int = 64, w: int = 96) -> np.ndarray:
    row = np.linspace(0, 255, w, dtype=np.float64)
    return np.tile(row, (h, 1)).astype(np.uint8)


def test_png_decodes_grayscale() -> None:
    src = _ramp_gray()
    img = CommonImage.from_bytes(_png_bytes(src), "scan.png")
    assert img.fmt == FORMAT_PNG
    assert img.data.dtype == np.uint8
    assert img.data.ndim == 2
    assert img.data.shape == src.shape
    np.testing.assert_array_equal(img.data, src)


def test_jpeg_decodes_grayscale() -> None:
    src = _ramp_gray()
    img = CommonImage.from_bytes(_jpeg_bytes(src), "scan.jpg")
    assert img.fmt == FORMAT_JPEG
    assert img.data.shape == src.shape


def test_jpeg_alias_extension() -> None:
    src = _ramp_gray()
    img = CommonImage.from_bytes(_jpeg_bytes(src), "scan.jpeg")
    assert img.fmt == FORMAT_JPEG


def test_png_upside_down_colors_preserved() -> None:
    src = _ramp_gray()[::-1, :]
    img = CommonImage.from_bytes(_png_bytes(src), "scan.png")
    np.testing.assert_array_equal(img.data, src)


def test_dicom_monochrome2_decodes() -> None:
    src = np.linspace(0, 5000, 64 * 96, dtype=np.float64).reshape(64, 96).astype(np.uint16)
    img = CommonImage.from_bytes(_dicom_bytes(src), "scan.dcm")
    assert img.fmt == FORMAT_DICOM
    assert img.data.ndim == 2
    assert img.data.dtype == np.uint8
    assert img.data.shape == src.shape
    assert img.data.max() == 255


def test_dicom_monochrome1_inverted() -> None:
    """MONOCHROME1 (white=minimum) must be bitwise-inverted like the legacy loader."""
    src = np.linspace(0, 4000, 64 * 64, dtype=np.float64).reshape(64, 64).astype(np.uint16)
    m2 = CommonImage.from_bytes(_dicom_bytes(src, photometric="MONOCHROME2"), "scan.dcm")
    m1 = CommonImage.from_bytes(_dicom_bytes(src, photometric="MONOCHROME1"), "scan.dcm")
    np.testing.assert_array_equal(m1.data, cv2.bitwise_not(m2.data))


def test_dicom_negative_values_clamped() -> None:
    src = (np.arange(64 * 96, dtype=np.int16).reshape(64, 96) - 3000)
    img = CommonImage.from_bytes(_dicom_bytes(src.astype(np.uint16)), "scan.dicom")
    assert img.data.dtype == np.uint8


def test_properties_shape_width_height() -> None:
    src = _ramp_gray(h=64, w=96)
    img = CommonImage.from_bytes(_png_bytes(src), "scan.png")
    assert img.shape == (64, 96)
    assert img.width == 96
    assert img.height == 64


def test_unsupported_extension_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported file type"):
        CommonImage.from_bytes(b"not an image", "scan.txt")


def test_garbage_png_rejected() -> None:
    from PIL import UnidentifiedImageError

    with pytest.raises(UnidentifiedImageError):
        CommonImage.from_bytes(b"definitely not a png", "scan.png")


def test_format_matches_legacy_loader_on_real_images() -> None:
    """Cross-check against the frozen oracle on real fixtures in Images/."""
    import pathlib

    import inference_engine as legacy

    root = pathlib.Path(__file__).resolve().parents[2] / ".."
    fixtures = [
        ("Images/dataset_x-ray1.png", "scan.png"),
        ("Images/high_noise_dicom.dicom", "scan.dcm"),
        ("Images/low_nosie_dicom.dicom", "scan.dcm"),
    ]
    for rel, name in fixtures:
        path = root / rel
        if not path.exists():
            continue
        data = path.read_bytes()
        legacy_img = legacy._load_image_from_bytes(data, name)
        new_img = CommonImage.from_bytes(data, name)
        assert new_img.data.shape == legacy_img.shape, rel
        np.testing.assert_allclose(new_img.data, legacy_img, atol=1, err_msg=rel)


def test_no_cv2_imread_needed_for_uint8_roundtrip() -> None:
    src = _ramp_gray(h=32, w=48)
    img = CommonImage.from_bytes(_png_bytes(src), "scan.png")
    ok, encoded = cv2.imencode(".png", img.data)
    assert ok
    assert len(encoded) > 0

# ADR-007: CommonImage — single image abstraction across formats

- **Status:** Accepted
- **Date:** 2026-08-05
- **Deciders:** Architecture review
- **Related:** [ADR-006-model-manager.md](ADR-006-model-manager.md)

## Context

The pipeline consumes PNG, JPEG, and DICOM. Legacy code mixed decoding,
normalization, and format-specific quirks (e.g. DICOM `MONOCHROME1` inversion)
inside `inference_engine._load_image_from_bytes`. Sprint 3 needs one place that
turns raw upload bytes into a normalized grayscale `uint8` array, with the
source format recorded so downstream stages (preprocessing, inference,
postprocessing) can stay format-agnostic.

## Decision

Introduce `CommonImage` in `worker/converters.py`:

- `.from_bytes(data: bytes, filename: str)` classmethod → decoded, normalized
  grayscale `uint8` ndarray plus the detected format.
- Handles PNG/JPEG via PIL (`convert("L")`) and DICOM via pydicom (scale to
  0–255, apply `cv2.bitwise_not` when `PhotometricInterpretation ==
  "MONOCHROME1"`), mirroring the legacy loader exactly.
- Returns image `shape`/`dtype` and format so callers never re-detect.
- No TensorFlow import — pure converter, unit-testable without the model.

## Rationale

- Mirrors the legacy loader bit-for-bit (this is the oracle contract) while
  making it importable and testable outside the request path.
- Single choke point for format quirks; downstream stages assume grayscale
  `uint8`.
- Keeps the worker free of eager ML imports during conversion.

## Alternatives considered

- **Keep legacy loader, copy into worker** — duplicates format logic and
  drifts from the oracle.
- **A `Format` enum passed everywhere** — still requires a decoder; CommonImage
  bundles decode + normalize + format.
- **Load via TensorFlow `tf.io`** — pulls TF into the hot conversion path and
  changes DICOM handling.

## Consequences

**Positive**
- One conversion contract, unit-testable per format (PNG/JPEG/DICOM incl.
  MONOCHROME1).
- Format recorded once; preprocessing/inference never re-detect.

**Negative**
- New abstraction layer to maintain; must stay synced with the legacy loader
  until decommissioning.

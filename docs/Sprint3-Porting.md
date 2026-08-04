# Sprint 3 — Porting the legacy inference engine

This document maps the frozen legacy implementation
(`backend/inference_engine.py`, `backend/main.py`) to the new worker modules.
It is the contract for Sprint 3: every ported stage must produce output
equivalent to the legacy code it replaces. The legacy files stay frozen
(`# LEGACY - FROZEN`) until the decommissioning sprint and act as the
reference oracle for verification.

Related ADRs: [ADR-006](adr/ADR-006-model-manager.md),
[ADR-007](adr/ADR-007-common-image.md), [ADR-008](adr/ADR-008-orchestrator.md).

## Function map

| Legacy (`inference_engine.py`) | New home | Notes |
|---|---|---|
| `_load_image_from_bytes(image_bytes, filename)` | `worker/converters.py` → `CommonImage.from_bytes(data, filename)` | Same decoding: PIL `convert("L")` for PNG/JPEG; pydicom + scale 0–255 + MONOCHROME1 `bitwise_not` for DICOM. Returns grayscale `uint8` + format. |
| `_detect_noise_level(image_array)` | `worker/preprocess.py` → `noise_detection(img)` (Canny 50/150 → dilate 5×5 → median blur 5 → `np.var` of flat residual) | Keep thresholds identical. |
| `_run_unet(raw_img, ai_model)` | `worker/inference.py` → `predict(model, img)` | 256×256 `reflect`-padded tiles; per-tile `/255`, `expand_dims((0,-1))`, `predict(verbose=0)`, stitch, crop; residual = `absdiff` + threshold(4) ×4. Run `predict` via `asyncio.to_thread`. |
| `_clinical_enhance(img)` | `worker/postprocess.py` → `enhance(img)` | `createCLAHE(clipLimit=1.0, tileGridSize=(8,8))` → GaussianBlur (5,5,1.0) → `addWeighted(1.1, -0.2, 0)`. |
| `_to_b64_png(img_array)` | `worker/postprocess.py` → `encode_png(img)` | `cv2.imencode(".png")` → base64 (no `data:` prefix in the worker; executor stores bytes). |
| `run_pipeline(image_bytes, filename, noise_threshold=8.0)` | `worker/orchestrator.py` → `run(data, *, fmt, model_manager)` | Orchestrates the stages above; bypass when `noise_variance <= noise_threshold`; returns `PipelineResult` with 4 encoded outputs + routing + timings. |
| `_load_model()` (lazy global) | `worker/model_manager.py` → `ModelManager` | `startup()` loads TF+weights once, records `model_versions`; `get_pipeline()` returns cached; `shutdown()`. |

## Stage ports (one commit each)

1. **3.1 converters** — `CommonImage` (+ format detection), no TF import.
   Gate: PNG/JPEG/DICOM unit tests pass; MONOCHROME1 inversion matches legacy.
2. **3.2 preprocessing** — 256-tiling helpers + Canny noise variance.
   Gate: `noise_detection` output matches legacy on `Images/` fixtures.
3. **3.3 model manager** — `ModelManager` startup/get_pipeline/shutdown.
   Gate: model loads once; memory stable; worker startup verified.
4. **3.4 inference** — tiled threaded `predict` with `asyncio.to_thread`.
   Gate: inference output matches legacy `_run_unet`.
5. **3.5 postprocessing** — CLAHE+USM + PNG encode + golden tests.
   Gate: enhanced image quality validated (`psnr > 35` AND `ssim > 0.95`,
   scikit-image); `@pytest.mark.golden`.
6. **3.6 orchestrator + executor** — rename seam to `orchestrator.run`,
   produce 4 outputs, persist `model_versions` / `scan.model_id` /
   `noise_variance` / `processing_time_ms` / `routing_message` /
   `was_bypassed`, mount weights in compose, remove `pipeline.py`.
   Gate: E2E upload → queue → worker → outputs stored → metadata updated →
   job completed. Only then tag `sprint-3`. ✅ done (7a106a0 + working tree,
   `77 passed` default suite, `3 passed` golden, E2E `test_worker.py` green).

## Outputs produced per scan

| Output type | Content | Persisted as |
|---|---|---|
| `ORIGINAL` | link to the uploaded object | existing Object row |
| `NOISE_MAP` | `residual_visual` (threshold ×4) | `ScanOutput` |
| `UNET` | raw U-Net output | `ScanOutput` |
| `ENHANCED` | CLAHE+USM final | `ScanOutput` |

## Verification checklist

- [x] CommonImage decodes `Images/dataset_x-ray1.png`, `Images/high_noise_dicom.dicom`, `Images/low_nosie_dicom.dicom`
- [x] `noise_variance` matches legacy `_detect_noise_level` (float, same thresholds)
- [x] Bypass vs AI routing matches `run_pipeline` (threshold 8.0)
- [x] Enhanced output `psnr > 35` AND `ssim > 0.95` vs legacy output (golden)
- [x] `model_versions` row created once with git commit; `scan.model_id` set
- [x] `scan.processing_time_ms` persisted from total orchestrator timing
- [x] `test_worker.py` happy path asserts 4 outputs + metadata + MinIO checksums

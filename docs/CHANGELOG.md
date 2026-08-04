# CHANGELOG

Human-readable engineering log. Newest first. Part of the Definition of Done:
every merged change that affects behavior, API, or infrastructure updates this
file.

## [Unreleased]

### Sprint 3 — Real ML pipeline (in progress, branch `sprint/3-real-ml`)

**Added**
- ADRs: `ADR-006-model-manager.md`, `ADR-007-common-image.md`,
  `ADR-008-orchestrator.md`.
- `docs/Sprint3-Porting.md` — legacy → new module map and verification gates.
- (stage 3.1) `worker/converters.py` — `CommonImage` unified PNG/JPEG/DICOM
  decoding.
- (stage 3.2) `worker/preprocess.py` — tiling + Canny flat-tissue noise
  variance.
- (stage 3.3) `worker/model_manager.py` — `ModelManager` load-once lifecycle +
  `model_versions` persistence.
- (stage 3.4) `worker/inference.py` — tiled threaded U-Net predict.
- (stage 3.5) `worker/postprocess.py` — CLAHE + unsharp masking + PNG encode;
  golden tests (scikit-image, PSNR>35 AND SSIM>0.95).
- (stage 3.6) `worker/orchestrator.py` — full pipeline coordinator producing
  ORIGINAL/NOISE_MAP/UNET/ENHANCED + routing + per-stage timings; executor
  rewritten to call it and persist `model_versions` / `scan.model_id` /
  `noise_variance` / `processing_time_ms` / `routing_message` /
  `was_bypassed`; `worker/main.py` starts `ModelManager` at boot; weights
  volume-mounted in compose; `worker/pipeline.py` removed.

**Changed**
- `backend/inference_engine.py`, `backend/main.py`, `backend/test_api.py`
  marked `# LEGACY - FROZEN` (no new features; removal after frontend
  migration).

## [Sprint 2B] — Async worker architecture

**Added**
- `worker/` package: `consumer.py`, `executor.py`, `main.py`, `pipeline.py`,
  `Dockerfile`.
- `tests/test_worker.py` (happy + failure paths).
- `deploy/docker-compose.yml` `worker` service.
- `ScanRepository.set_running()`.

**Fixed**
- `gateway/core/queue.py`: first publish crashed because `_publish` resolved
  the exchange object before the lazy connect. It now resolves the exchange by
  name after connecting.

## [Sprint 2A] — Uploads & scans domain

**Added**
- `gateway/domains/scans/` — `router.py`, `service.py`; `schemas/scan.py`.
- `tests/test_scans.py`.
- `ScanRepository.soft_delete()`.

**Changed**
- Upload validation chain (extension → magic bytes → MIME → decode →
  dimensions → size → SHA-256 → object upload); Job created in QUEUED;
  `inference.run` published after commit (broker-outage-safe).

## [Sprint 1] — Auth, infra, design

- PostgreSQL + Redis + RabbitMQ + MinIO compose stack.
- JWT auth (access + refresh, logout blacklist, register/login/me).
- Architecture, security, database, ADR docs.
- `# LEGACY - FROZEN` does not apply yet at this point (legacy app predates).

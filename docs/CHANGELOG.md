# CHANGELOG

Human-readable engineering log. Newest first. Part of the Definition of Done:
every merged change that affects behavior, API, or infrastructure updates this
file.

## [Unreleased]

### Sprint 4C — CI/CD (branch `sprint/3-real-ml`)

**Added**
- GitHub Actions CI — two workflows (`docs/engineering/ci.md`):
  - `ci.yml` (fast, push → `sprint/**`): ruff → mypy → pytest (unit +
    integration) and tsc → eslint, grouped, with `cancel-in-progress`.
  - `ci-full.yml` (merge gate, PR→main / push→main / manual): validate →
    (backend incl. golden, frontend) → Docker build → **Playwright E2E last**,
    with failure-artifact upload (trace ZIPs + HTML report). Manual dispatch
    additionally runs the CPU baseline benchmark.
- `backend/ruff.toml` — the lint gate (`ruff check .` from `backend/`) is now
  fully clean; `# LEGACY - FROZEN` modules and alembic-generated migrations are
  excluded by config, not by editing frozen code.
- ADR-011 Model Artifact Distribution — weights served from GitHub Release
  `weights-v1`, downloaded in CI via `GITHUB_TOKEN`, verified against a
  committed manifest (`scripts/weights.sha256`: filename + size + SHA-256) so a
  missing/corrupt asset fails the pipeline instead of silently skipping tests.
- `scripts/verify_all.sh` — local gate runner that mirrors `ci-full.yml`
  stage-for-stage (compose validate → weights → ruff → mypy → pytest → golden →
  tsc → eslint → e2e), keeping CI and local verification aligned.
- `backend/requirements-dev.txt` — pinned ruff/mypy/pytest tooling for CI and
  local dev.
- `docs/engineering/ci.md` — workflow overview, trigger table, secrets
  (none beyond `GITHUB_TOKEN`), weights release process, cache strategy, rerun
  instructions, and local equivalent commands.

**Fixed**
- Scheduler test flake (root cause): `republish_retries`/`recover_stalled`
  count *every* due `RETRYING` row in the shared persistent `jobs` table, and
  six tests assert those global counts — rows left by earlier runs made the
  suite order- and history-dependent. `tests/test_scheduler.py` now runs an
  autouse `DELETE FROM jobs` fixture (safe: `jobs` is a leaf table) so each
  test starts from a clean state. Deterministic across repeated runs.
- Ruff I001 import ordering in `gateway/models/job.py`.
- Ruff UP017 in `gateway/core/observability/logging.py` and the two benchmark
  scripts (`timezone.utc` → `UTC` alias) surfaced by the now-clean lint gate.
- Dockerized-stack boot bugs surfaced by the full `verify_all.sh` run:
  - Gateway container crashed at startup — `EmailStr` in the auth schemas
    needs `email-validator`, which `requirements.txt` did not install (the
    `pydantic[email]` extra only). Added as an explicit top-level dependency.
  - Worker container crash-looped — the weights bind-mount source in
    `deploy/docker-compose.yml` resolved one directory too shallow
    (Compose resolves relative paths from `deploy/`, so `../../` is required
    for the repo-root weights). Corrected; model now loads from `/weights`.

### Sprint 4B — Observability (branch `sprint/3-real-ml`)

**Added**
- `gateway/core/observability/` — the vendor-facade seam: `logging.py`
  (structured JSON + correlation context), `metrics.py` (Prometheus facade +
  no-op when disabled), `tracing.py` (OpenTelemetry tracing-only facade with
  W3C `traceparent` propagation; disabled mode is a no-op).
- `TraceIDMiddleware` (`gateway/core/otel.py`) — request runs inside a span
  that continues the incoming `traceparent`; the OTel trace id becomes the
  correlation `trace_id` when tracing is on.
- W3C propagation: `queue.py:build_message_headers` injects the active span's
  `traceparent`; the worker continues remote traces
  (`worker/inference.run`, `worker.process_job`, five `pipeline.*` stage
  spans, `scans.upload.persist`).
- ADR-010-observability.
- Deploy overlay (`deploy/observability.yml`): otel-collector (traces),
  prometheus (scrape), grafana (datasource provisioned) + env overrides that
  switch gateway/worker/scheduler onto OTLP tracing + Prometheus metrics.
  Core stack runs without it.
- `deploy/docker-compose.test.yml` — app services gated behind the `app`
  compose profile (infra-only bring-up for the pytest suite).
- `infrastructure/` configs: otel-collector, prometheus scrape, grafana
  datasource — validated against the real binaries (`promtool`,
  `otelcol validate`).
- `scripts/benchmark_observability.py` + `docs/benchmarks/observability-overhead.md`
  — perf gate: **+0.55%** end-to-end overhead (tracing off vs on, PASS < 5%).
- Per-phase reviews: `docs/reviews/sprint-4b-phase{1,2,3,4}-review.md`.
- OTel deps (`opentelemetry-api/sdk/exporter-otlp-proto-http`, tracing-only,
  justified in `requirements.txt`).

**Fixed**
- `OTLPSpanExporter` silent span-drop: an explicitly-passed endpoint is used
  verbatim by the SDK (only the env-var default path gets `/v1/traces`
  appended), so a bare `http://collector:4318` POSTed to `/` → 404 → every
  span dropped. The facade now appends the signal path itself
  (`_otlp_http_endpoint`), caught by the Phase 4 deploy smoke test against a
  real collector, pinned by `test_otlp_http_endpoint_appends_signal_path`.
- `@contextmanager` no-op bodies use a plain `yield` (a `yield from
  contextlib.nullcontext()` raises `TypeError`).
- `gateway/main.py` startup log read `storage.bucket`, which is not part of the
  `StorageProvider` contract (only the MinIO provider sets it); it now logs the
  configured `settings.s3_bucket`. Removes the last full-repo mypy error in a
  scoped file (rest tracked in `docs/technical-debt.md`).

**Changed**
- `gateway/main.py`, `worker/main.py`, `scheduler/main.py` — `tracer.shutdown()`
  in teardown; `init_observability` wires `service`/`otel_exporter`/`otel_endpoint`.
- Observability is a removable overlay: `docker compose -f
  deploy/docker-compose.yml -f deploy/observability.yml up -d --build` for the
  full stack + observability.

### Sprint 4A — Distributed scheduler (branch `sprint/3-real-ml`)

**Added**
- `scheduler/` package: `main.py` (retry + stall-recovery + cleanup loops),
  `retry_jobs.py` (due-retry republish, stale-RUNNING recovery, unconfirmed-
  marker recovery, atomic DB claim), `cleanup.py`, `consumer.py`
  (`cleanup.run` handler), `metrics.py`, `healthcheck.py` (heartbeat-staleness
  check), `Dockerfile`.
- ADR-009-scheduler.
- `scheduler.cleanup` durable queue bound to `commands`/`cleanup.run`;
  commands and the internal timer share one `CleanupService.run_cleanup`
  implementation guarded by a Redis distributed lock (`SET NX PX` +
  compare-and-delete Lua release) with duration/deleted/archived/failure/skipped
  metrics.
- `tests/test_scheduler.py` — republish/stall/unconfirmed/idempotency + cleanup
  (rows + S3 purge, lock-held skip, lock release, `cleanup.run` source).
- `deploy/docker-compose.yml` — `gateway` and `scheduler` first-class services
  (healthchecks, `restart: unless-stopped`, `depends_on` healthy infra);
  gateway applies migrations on start.
- `gateway/core/config.py` — `scheduler_cleanup_lock_ttl_seconds`.

**Changed**
- Scheduler retry/cleanup passes no longer run inside the gateway; they live in
  the dedicated scheduler process. Cleanup is idempotent and safe against
  concurrent runs (single implementation, distributed lock, trigger source
  logged).

### Sprint 3.5 — First authenticated frontend journey (branch `sprint/3-real-ml`)

**Added**
- Auth UI: `src/app/signin/page.tsx` (login/register toggle, validation, session
  redirect), `src/lib/auth.tsx` `AuthProvider`/`useAuth` (restore via `me()`,
  fallback `refreshSession()`; `signIn`/`signUp`/`signOut`), auth-aware
  `Navbar` (gallery link, avatar, sign in/out).
- Rewritten `src/lib/api.ts`: `ApiError`, token storage
  (`denoisex_access_token`), `request()` with `credentials:"include"` and
  401→refresh retry, typed `Scan`/`ScanList`/`Job`/`User`/`OutputUrl` helpers,
  `pollJob(jobId, onUpdate)` with cancel handle, `checkHealth` → `/health/live`.
- `src/app/denoise/page.tsx`: auth gate → upload → `uploadScan` (202) →
  `pollJob` (300s timeout) → results page with routing banner, inference
  report, and 4 `OutputCard`s (ORIGINAL / NOISE_MAP / UNET / ENHANCED via
  presigned URLs).
- `src/app/gallery/page.tsx`: scan history (`listScans(0,50)`), status chips,
  expandable scan cards rendering the 4 outputs, refresh.
- `src/components/OutputCard.tsx`: shared presigned-URL image card (expand
  overlay, dark processing state, `output-*`/`download-*` ids).
- Playwright E2E smoke (`frontend/e2e/smoke.spec.ts` + config + PNG fixture +
  README): register/login → upload → poll to COMPLETED → 4 outputs → download
  URLs → gallery → logout. Green against live Docker infra.
- `backend/scripts/benchmark_cpu.py`: CPU baseline via `worker.orchestrator.run`
  reusing `StageTimings`; report at `docs/benchmarks/cpu-baseline.md` (Apple M2,
  3 runs/image: bypass ~25–1,600 ms; heavy DICOM PATH A ~28 s inference).
- Idempotent duplicate-upload dedup: per-org partial unique index
  `(organization_id, content_hash) WHERE deleted_at IS NULL` (migration
  `13183f85304c`). Re-uploading identical bytes in the same org returns HTTP 200
  with `duplicate: true` and reuses the existing scan + outputs — no new object
  upload, no new job, no republish (IntegrityError race falls back to re-reading
  the existing scan). Frontend shows an amber duplicate banner.
- E2E re-runnability: dependency-free in-test PNG fixture
  (`frontend/e2e/lib/png.ts`, `makeUniqueFixture`) and a persistent
  env-driven account (`E2E_EMAIL`/`E2E_PASSWORD`) sidestep the 3/day/IP
  register rate limit.

**Changed**
- `POST /api/v1/scans` response contract: full `scan` object + nullable
  `job_id`/`job_status` + `duplicate`/`message`; `202` (accepted) vs `200`
  (duplicate) documented in `docs/api/openapi.yaml`, which now lints with 0
  errors (3.1-validated: refs resolved, `nullable` → `type: [x, "null"]`,
  malformed flow-style descriptions and missing response descriptions fixed).

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

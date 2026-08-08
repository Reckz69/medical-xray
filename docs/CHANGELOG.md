# CHANGELOG

Human-readable engineering log. Newest first. Part of the Definition of Done:
every merged change that affects behavior, API, or infrastructure updates this
file.

## [Unreleased]

### Sprint 4F — Operational health + full frontend coverage

**Added**
- `GET /health/infra` (read-only, hidden from public OpenAPI): aggregated
  operational matrix — `status`/`checked_at`, `app_version`, `git_sha`
  (captured once at import via `gateway/core/buildinfo.py`), `model_version`,
  `checks` (postgres/redis/rabbitmq/storage), `worker` (alive, last heartbeat,
  model loaded/name/version, gpu), and `rabbitmq` (queue name + best-effort
  depth). Returns 200 ok / 503 degraded; optional diagnostics (`queue_depth`,
  `git_sha`) degrade to null instead of failing.
- Worker heartbeat registry (`gateway/core/worker_registry.py`): versioned
  payload (`schema_version: 1`, uptime, model, gpu, `capabilities`),
  Redis `worker:active` set + per-worker heartbeat key, gateway-side pruning of
  stale members. Redis is telemetry-only — failures never raise or crash the
  worker. Scheduler-independent eventual consistency: a crashed worker's key
  expires via TTL and is pruned on next read.
- Config knobs (`gateway/core/config.py`): `app_version`, `git_sha`,
  `health_infra_auth` (default ON in production only), worker heartbeat
  interval/TTL.
- Worker heartbeat loop wired in `worker/main.py` + rewritten `worker/heartbeat.py`.
- `backend/tests/test_health_infra.py` (6 tests): payload schema, registry
  stale-pruning, endpoint contract, degraded-when-worker-dead, queue-depth-null
  degradation, and the configurable auth gate. Full backend suite green
  (142 passed / 3 deselected).
- Frontend: auth-aware shell (mobile menu, user dropdown, Toaster/sonner,
  `next-themes` wiring), `/dashboard` (live summary cards, infra matrix, recent
  scans, statistics via `useLiveScans`/`useInfraHealth`), `/status` (full infra
  matrix with `checked_at` age + 401→`/health/ready` fallback), `/gallery`
  (metadata-rich cards, before/after `ScanViewer`, soft-delete with confirm,
  pagination, live polling), denoise job timeline (real transitions), `/profile`,
  `/settings` (localStorage prefs: poll interval, grid density, theme), functional
  `/feedback` (GitHub Issues + mailto), `/about` (Model Version + MIT License),
  auth-aware landing (`/` redirects signed-in users to `/dashboard`).
- Frontend API surface (`src/lib/api.ts`): `checkReady`, `checkInfra` (returns
  the degraded 503 body rather than throwing; throws only on 401/403 — so the
  401→`/health/ready` fallback actually triggers — or an unparseable payload),
  `deleteScan`, `forgotPassword`.
- `frontend/e2e/smoke.spec.ts` extended: dashboard + status matrix +
  feedback/about links, gallery soft-delete flow, and the signed-out status
  auth gate (4 tests, green against the live stack).

**Changed**
- `frontend/src/app/page.tsx`: signed-in visitors redirect to `/dashboard`.
- `docs/engineering/deployment.md`: `/health/infra` contract, heartbeat registry
  and eventual-consistency documented.
- `docs/api/openapi.yaml`: `/scans/{id}/outputs/{type}/url` plural path corrected.

**Known gaps (recorded, not fixed)**
- `/api/v1/auth/forgot-password` remains an acknowledge-only placeholder (no
  email delivery yet) — the frontend wires the call, not the reset flow.

### Sprint 4E — Production readiness (runtime configuration)

**Added**
- Runtime configuration (ADR-018): one compose stack for every environment —
  `.env` selects local vs cloud via `SITE_DOMAIN`, `CADDYFILE`, `COMPOSE_PROFILES`,
  `CORS_ORIGINS`, `S3_PUBLIC_ENDPOINT`, `MODEL_WEIGHTS_PATH`. No LOCAL/CLOUD
  branches in code.
- `S3_PUBLIC_ENDPOINT` runtime knob (ADR-003/ADR-018): presigned download URLs
  are issued against the browser-reachable `s3.<SITE_DOMAIN>` Caddy edge
  (`s3.*` → `minio:9000`, no gzip) instead of the internal endpoint; MinIO SDK
  path-style restriction documented (subdomain required). Empty → internal
  presign (tooling only).
- `Caddyfile.local` (Sprint 4E local mode): Caddy internal CA (`local_certs`),
  same `api.`/`s3.`/root site topology as the cloud `Caddyfile`.
- Containerized frontend (ADR-018 profile): `frontend/Dockerfile`
  (`output: "standalone"`, non-root `nextjs` runner) + `.dockerignore`;
  `COMPOSE_PROFILES=frontend` includes it, Caddy proxies `<SITE_DOMAIN>` →
  `FRONTEND_UPSTREAM`. Same standalone build runs on Vercel in cloud mode.
- Jaeger observability (ADR-010 overlay): `jaeger` v2 (2.20.0) service with a
  loopback-bound UI in `deploy/production/observability.yml` +
  `backend/deploy/observability.yml`; collector dual-exports
  `[debug, otlp_http/jaeger]` (gRPC `otlp/jaeger` mismatched Jaeger's HTTP
  receiver). Verified: cross-service trace gateway → worker → pipeline.
- ADR-018 `docs/adr/ADR-018-runtime-configuration.md`; `docs/README.md` ADR log
  and index updated.

**Changed**
- `deploy/production/.env.example`: Sprint 4E runtime-config blocks (LOCAL vs
  CLOUD), `S3_PUBLIC_ENDPOINT`, lowercase registry (`ghcr.io/reckz69`),
  compose-relative weights default `../../n2n_unet_best_weights04.keras`.
- `docker-compose.yml`: `S3_PUBLIC_ENDPOINT` gateway env, frontend profile
  service + healthcheck (IPv4 `127.0.0.1` — busybox wget resolves `localhost`
  → `::1`, Next standalone binds IPv4), both Caddyfiles gain the `s3.` site.
- `backend/gateway/core/config.py` + `storage/minio_provider.py`:
  `s3_public_endpoint` setting and dedicated presign client bound to it.
- `.github/workflows/ci-images.yml` + ADR-016: owner lowercased
  (`${{ lower(github.repository_owner) }}`) — Docker refs are lowercase-only;
  GHCR normalizes case so behavior is unchanged.
- `docs/engineering/deployment.md`: runtime-configuration section, `s3.` edge
  + frontend in topology/sequence, provisioning covers both modes + `s3.` DNS.
- `docs/engineering/backup-restore.md`: RabbitMQ export/import now passes
  explicit `-u/-p` (default user is `denoise`, not guest/guest — plain
  `rabbitmqadmin export` gets `Access refused`); MinIO backup/restore passes
  `.env` values explicitly; restore verification includes presigned download
  via the `s3.` edge (proven 2026-08-08).
- `docs/engineering/ci.md`: lowercase owner normalization note.
- `docs/engineering/production-checklist.md`: `s3.` DNS + presigned-download
  boxes, Jaeger trace verification, 4E restore-tested evidence.

**Proven on the live local deployment (Phase 2 gate, 2026-08-08)**
- HTTPS E2E: frontend 200, `health/ready` all-ok, PATH A inference COMPLETED,
  presigned downloads 200 with checksums matching the API.
- Backup: Postgres `pg_dump -Fc`; MinIO `mc mirror` (16 objects); RabbitMQ
  definitions export.
- Restore: Postgres wipe → `pg_restore --clean --if-exists` (counts exact);
  MinIO delete → mirror-back (byte-for-byte); RabbitMQ import (queue/exchanges/
  binding/user restored).
- `docker compose down` → `up`: named volumes persisted, all data intact,
  full stack healthy.

**Known gaps (recorded, not fixed — see production-checklist)**
- SR-3 hardening: compose images still run as root with unpinned deps; k8s
  reference manifests still carry uppercase `ghcr.io/Reckz69` image refs
  (harmless to GHCR but inconsistent with ADR-016).
- WAL/PITR for Postgres documented as follow-on; nightly logical dumps only.

### Sprint 4D — Production readiness

**Added**
- Production Compose (ADR-012): `deploy/production/docker-compose.yml` — Caddy
  as the only exposed edge (ADR-013), `image:`+`build:` seam for pull-from-GHCR
  or build-from-source deploys (ADR-016), `${VAR:?}` required secrets,
  weights mounted `:ro`, healthchecks/restart policies, and
  `deploy/production/.env.example` + `generate-secrets.sh`
  (`chmod 600`, no committed creds — ADR-014).
- `deploy/k8s/` reference manifests (Compose → K8s mapping, documented
  alternative) and `deploy/terraform/` scaffold (labeled not
  production-ready; IaaS choice deferred).
- `ci-images.yml` — GHCR image publishing (ADR-016/017): build + push per
  service matrix, 4-tag scheme (`latest`, `<sha>`, `v<semver>`,
  `<sprint-tag>`), `permissions: packages: write`, buildx `type=gha` cache.
- ADRs 012–017: deployment architecture, HTTPS ingress, secrets management,
  persistent state, image registry, versioning/release.
- Ops docs: `docs/engineering/deployment.md` (bring-up, upgrade, rollback,
  HTTPS sequence), `backup-restore.md` (RPO ≤ 24 h / RTO ≤ 4 h, nightly
  pg_dump/mc mirror/rabbitmqadmin export, off-site copy requirement, restore
  runbook, object lifecycle), `secret-rotation.md` (JWT/Postgres/RabbitMQ/
  MinIO/Grafana/GHCR runbooks), `production-checklist.md` (decision-forcing
  readiness checklist with SR-1..5 coverage table), `scaling.md` (single-VM
  ceiling, K8s path reference).

**Changed**
- `docs/engineering/ci.md` synced with `ci-images.yml`: overview ASCII,
  trigger table (push `main` → ci-full + ci-images; `v*`/`sprint-*` tags →
  ci-images), `packages: write` permissions note, image tag table, GHCR
  cache/duration strategy (ADR-016/017).
- `docs/README.md` index: engineering section now lists deployment, scaling,
  backup-restore, secret-rotation, production-checklist.

**Known gaps (recorded, not fixed — see production-checklist)**
- SR-3 hardening: compose images run as root with unpinned `requirements.txt`;
  non-root/read-only-root/pinned-tag rollout and SAST/SCA scheduled (SR-5).
- WAL/PITR for Postgres documented as follow-on; nightly logical dumps only.

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
- Fast `ci.yml` backend job never downloaded the weights, so the
  model-dependent unit+integration suite (real worker) failed on every push —
  it now downloads and verifies `weights-v1` like the full gate.
- Model artifact canonicalized to `n2n_unet_best_weights04.keras`: GitHub
  Release asset names are sanitized (space → `.`, parens stripped), so the
  `(2)`-suffixed name could not be stored. Renamed the release asset, the
  gitignored local file, and every reference (manifest, compose, config,
  workflows, tests, docs) to the clean name — removing the space/paren
  footguns that caused the two boot bugs above.

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

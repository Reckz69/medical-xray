# Sprint 4E — Review: Production readiness (runtime configuration)

- **Status:** Review-complete, ready to tag `sprint-4e` and push
- **Date:** 2026-08-08
- **Branch:** `main`
- **Related:** [ADR-018](../adr/ADR-018-runtime-configuration.md), [ADR-003](../adr/ADR-003-presigned-urls.md), [ADR-010](../adr/ADR-010-observability.md), [ADR-011](../adr/ADR-011-model-artifacts.md), [ADR-013](../adr/ADR-013-https-ingress.md), [ADR-016](../adr/ADR-016-image-registry.md), `docs/engineering/deployment.md`, `docs/engineering/backup-restore.md`, `docs/engineering/ci.md`, `docs/engineering/production-checklist.md`

## Goal

Prove the production compose stack as a **runtime-configurable** deployment on a
real local Docker host (ADR-018): frontend container, Caddy local + cloud modes,
Jaeger observability, `.env`-driven knobs — then execute the Phase-2 merge-gate
(backups → restore/DR → down/up persistence), update the ops docs, and tag
`sprint-4e`.

## Delivered

### Phase 1 — Runtime-configuration production stack

- **Frontend container** (`output: "standalone"`): `frontend/Dockerfile`
  (node:22-alpine builder → non-root `nextjs` runner; `NEXT_PUBLIC_API_URL`
  build arg; `.next/standalone` + `public` + `.next/static`) + `.dockerignore`.
- **Compose/Caddy**: `caddy` wired to `${CADDYFILE}` (ADR-013/018); new
  `Caddyfile.local` (Caddy internal CA, `local_certs`) structurally identical
  to the cloud `Caddyfile`; both now define `s3.{$SITE_DOMAIN}` → `minio:9000`
  **without gzip** (verbatim S3 objects, ADR-003). `frontend` profile service
  with `NEXT_PUBLIC_API_URL` default `https://api.${SITE_DOMAIN}`.
- **`S3_PUBLIC_ENDPOINT` knob** (ADR-003/018): browser-reachable origin for
  presigned download URLs. `config.py` adds `s3_public_endpoint`; the provider
  builds a second `_presign_client` bound to it (fallback: internal endpoint).
  MinIO SDK rejects path-style endpoints → the `s3.<SITE_DOMAIN>` subdomain.
- **Jaeger (v2, 2.20.0)** in `deploy/production/observability.yml` +
  `backend/deploy/observability.yml`: loopback-bound UI (`127.0.0.1:16686`);
  collector dual-exports `[debug, otlp_http/jaeger]`. The gRPC default
  (`otlp/jaeger`) mismatched Jaeger's HTTP receiver — fixed by the
  `otlp_http/jaeger` alias.
- **`.env` / `.env.example`**: LOCAL default block (`SITE_DOMAIN=localhost`,
  `CADDYFILE=Caddyfile.local`, `COMPOSE_PROFILES=frontend`,
  `CORS_ORIGINS=["https://localhost"]`,
  `S3_PUBLIC_ENDPOINT=https://s3.localhost`,
  `MODEL_WEIGHTS_PATH=../../n2n_unet_best_weights04.keras` — compose-relative,
  not `$PWD`); CLOUD block documented. `.env` regenerated with
  `generate-secrets.sh` (chmod 600, unique creds).
- **Registry lowercase** (ADR-016): `ghcr.io/reckz69/...` in compose +
  `.env.example` + `ci-images.yml` (`${{ lower(github.repository_owner) }}`).
  Docker image refs are lowercase-only; GHCR normalizes case so behavior is
  unchanged.

### Phase 2 — Merge-gate validation (executed on the live stack)

- **Stack up + healthy**: 13 containers + one-shot `minio-init`, all
  healthy/up; HTTPS E2E: frontend 200 at `https://localhost`,
  `health/ready` all-ok, auth 401 on unauthenticated `/api/v1/*`.
- **Full inference E2E**: registered user, uploaded high-noise DICOM → **PATH A
  engaged** (Var 8.1, "AI Denoising Engaged"), job COMPLETED; presigned
  download via `https://s3.localhost` → HTTP 200, checksum matches the API.
- **Jaeger**: services `[gateway, jaeger, worker]`; cross-service trace
  `gateway POST /api/v1/scans → worker.inference.run → worker.process_job →
  pipeline.{convert,preprocess,inference,postprocess,encode}`.
- **Backups**: Postgres `pg_dump -Fc` (10,744 B); MinIO `mc mirror` (16 files,
  13.4 MiB); RabbitMQ `rabbitmqadmin export` with explicit `-u/-p` (default
  guest/guest is refused; default user is `denoise`).
- **Restore/DR**:
  - MinIO: deleted a scan's outputs (16→13) → `mc mirror --overwrite` back →
    count 16, restored object sha256 byte-identical to the backup;
    DB↔MinIO key alignment 16/16.
  - Postgres: truncated + dropped all tables → documented
    `gunzip -c | pg_restore --clean --if-exists` → counts exact
    (users 1, scans 4, jobs 4, objects 16, scan_outputs 16).
  - RabbitMQ: `rabbitmqadmin import` → queue/exchanges/binding/user restored.
  - **Down→up persistence**: `docker compose down` (6 named volumes retained)
    → `up` → all healthy, counts/objects/topology intact.
- **Fresh E2E on the restored stack**: new user → upload → PATH A COMPLETED →
  presigned download 200; ENHANCED.png sha256 matches the API checksum exactly.
  (The register rate limit — 3/day/IP — was exercised during DR; cleared the
  ephemeral `rl:register:*` Redis counter to continue, consistent with
  Redis-as-ephemeral ADR-015.)

### Phase 3 — Docs

- `docs/adr/ADR-018-runtime-configuration.md` (new) — decision + knob table +
  mechanisms + alternatives + consequences.
- `docs/engineering/deployment.md` — runtime-configuration section, `s3.` edge
  + containerized frontend in topology/sequence diagrams, provisioning covers
  LOCAL vs CLOUD + `s3.` A record, Jaeger in ports matrix.
- `docs/engineering/backup-restore.md` — RabbitMQ export/import creds fixed,
  MinIO `.env` passing form, restore verified via the `s3.` edge, 4E proof note.
- `docs/engineering/ci.md` — lowercase owner normalization (ADR-016).
- `docs/engineering/production-checklist.md` — `s3.` DNS + presigned-download
  boxes, Jaeger trace verification, 4E restore-tested evidence, SR-5 schedule.
- `docs/README.md` + `docs/CHANGELOG.md` — ADR-018 in log; Sprint 4E entry.

## Decisions

1. **Runtime configuration, not environment branches (ADR-018)** — one compose
   stack, `.env` is the only thing that changes. Proven by running it: the local
   deployment *is* the prod topology.
2. **Presigned URLs go through the Caddy edge on a dedicated subdomain** —
   `s3.<SITE_DOMAIN>` (no gzip) with `S3_PUBLIC_ENDPOINT` controlling the
   public origin; MinIO SDK's path-style restriction made the subdomain
   mandatory, and Caddy issues the cert for it (local_certs locally, ACME in
   cloud).
3. **Jaeger is a config-only overlay (ADR-010/013)** — loopback-bound UI; the
   collector exports via `otlp_http/jaeger` because gRPC `otlp/jaeger` does not
   match Jaeger v2's HTTP receiver.
4. **Backup/restore commands must run as-documented** — the RabbitMQ export
   and MinIO cred passing were corrected to the forms proven on the live stack
   (explicit `-u/-p`; explicit `-e "VAR=$VAR"` from `.env`); the restore runbook
   now includes a presigned-download check through the `s3.` edge.
5. **Redis rate-limit state is disposable** — clearing `rl:register:*` to
   continue a test is fine because Redis is cache/rate-limit only (ADR-015);
   Postgres + the object store are the durable truth and were the DR focus.

## Validation

- Live Phase-2 gate green on the local deployment (details above), including a
  second full inference + download after the restore drill.
- `docker compose -f docker-compose.yml -f observability.yml config -q` — OK
  (perfomed earlier in 4E with the generated `.env`).
- Docs cross-checked against the actual compose/Caddyfiles/.env.example —
  variable names, service names, and edge hostnames all match.

## Remaining

- Tag `sprint-4e`, push `main` + tag to `denoisex`.
- Known gaps carried forward (production-checklist): SR-3 hardening (non-root,
  read-only-root, pinned deps), WAL/PITR follow-on, k8s reference manifests
  still uppercase `ghcr.io/Reckz69` (harmless to GHCR, inconsistent with
  ADR-016), SAST/SCA (SR-5) scheduled for a security sprint.

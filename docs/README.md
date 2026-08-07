# Denoise X — Design Documentation

Design artifacts for the Denoise X platform. These documents are the blueprint
agreed in the architecture review and MUST stay in sync with the codebase as it
evolves.

## Index

| Area | Document | Contents |
|---|---|---|
| Architecture | [`architecture/system-architecture.md`](architecture/system-architecture.md) | Components, responsibilities, data flow |
| Architecture | [`architecture/sequence-upload.md`](architecture/sequence-upload.md) | Upload → queue sequence |
| Architecture | [`architecture/sequence-inference.md`](architecture/sequence-inference.md) | Worker inference sequence |
| Architecture | [`architecture/sequence-download.md`](architecture/sequence-download.md) | Presigned-URL download sequence |
| Architecture | [`architecture/sequence-login.md`](architecture/sequence-login.md) | Login + token refresh sequence |
| API | [`api/openapi.yaml`](api/openapi.yaml) | OpenAPI contract (envelope + error codes) |
| Database | [`database/er.md`](database/er.md) | PostgreSQL ER diagram (9 tables) |
| Security | [`security/threat-model.md`](security/threat-model.md) | STRIDE threat model |
| Engineering | [`engineering/ci.md`](engineering/ci.md) | CI/CD workflows, weights release, local equivalents |
| ADRs | [`adr/`](adr/) | Architecture Decision Records |

## ADR log

| ADR | Decision | Status |
|---|---|---|
| [ADR-001](adr/ADR-001-postgresql.md) | PostgreSQL over MongoDB | Accepted |
| [ADR-002](adr/ADR-002-rabbitmq.md) | RabbitMQ for async job queue | Accepted |
| [ADR-003](adr/ADR-003-presigned-urls.md) | Presigned URLs over image proxying | Accepted |
| [ADR-004](adr/ADR-004-server-side-encryption.md) | Server-side encryption over app-level AES-GCM | Accepted |
| [ADR-005](adr/ADR-005-uuid-keys.md) | UUID primary keys everywhere | Accepted |
| [ADR-006](adr/ADR-006-model-manager.md) | ModelManager load-once lifecycle | Accepted |
| [ADR-007](adr/ADR-007-common-image.md) | Unified CommonImage for PNG/JPEG/DICOM | Accepted |
| [ADR-008](adr/ADR-008-orchestrator.md) | Orchestrator owns the pipeline flow | Accepted |
| [ADR-009](adr/ADR-009-scheduler.md) | Distributed scheduler for retry/stall/cleanup | Accepted |
| [ADR-010](adr/ADR-010-observability.md) | Tracing-only OTel, Prometheus metrics, removable overlay | Accepted |
| [ADR-011](adr/ADR-011-model-artifacts.md) | Model weights via GitHub Releases + SHA-256 gate | Accepted |
| [ADR-012](adr/ADR-012-deployment-architecture.md) | Production = Compose on a VM; K8s documented alternative | Accepted |
| [ADR-013](adr/ADR-013-https-ingress.md) | HTTPS via Caddy (ACME) at the edge; plain HTTP internal | Accepted |
| [ADR-014](adr/ADR-014-secrets-management.md) | Generated secrets in `.env`/compose secrets; no committed creds | Accepted |
| [ADR-015](adr/ADR-015-persistent-state.md) | Self-hosted Postgres/Redis/RabbitMQ/MinIO; managed documented alt | Accepted |
| [ADR-016](adr/ADR-016-image-registry.md) | GHCR image registry (reverses ADR-011 deferral) | Accepted |
| [ADR-017](adr/ADR-017-versioning-release.md) | Semver + sprint tags + image tags + weights/schema compatibility matrix | Accepted |

## Conventions that apply to all artifacts

- **All primary keys are UUIDs** (`gen_random_uuid()`), never auto-increment.
- **PostgreSQL is the source of truth.** Redis is a cache/rate-limiter only.
- **RabbitMQ has two topic exchanges:** `commands` and `events`.
- **Every `/api/v1/*` response uses the envelope** `{ success, data, meta, trace_id }`.
- **Every error** is `{ code, message, trace_id, status }` — never a bare HTTP status text.
- **Everything is soft-deletable** (`deleted_at`, `deleted_by`); permanent deletion only via `scheduler/cleanup.py`.

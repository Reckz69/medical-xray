# System Architecture

> Status: Accepted — Phase 0 design artifact
> This is the target-state architecture for Denoise X. The "Gateway" today is a
> single FastAPI modular-monolith process; the split from the Application layer
> is deferred but kept possible by naming and isolation conventions.

## Context diagram

```
                          ┌───────────────────────────────┐
                          │          Internet             │
                          └──────────────┬────────────────┘
                                         │ HTTPS
                          ┌──────────────▼────────────────┐
                          │      Cloudflare / WAF         │
                          └──────────────┬────────────────┘
                                         │
                          ┌──────────────▼────────────────┐
                          │   Load Balancer / Nginx       │
                          └──────────────┬────────────────┘
                                         │
                    ┌────────────────────▼─────────────────────┐
                    │         GATEWAY (FastAPI)                │
                    │  modular monolith · domains · repos      │
                    └──┬────────┬────────┬──────────┬──────────┘
                       │        │        │          │
                ┌──────▼───┐ ┌──▼─────┐ ┌▼────────┐ ┌▼───────────┐
                │PostgreSQL│ │ Redis  │ │RabbitMQ │ │MinIO / S3  │
                │ (truth)  │ │(cache, │ │ commands│ │ (SSE,      │
                │          │ │ limits)│ │ + events│ │  presign)  │
                └──────────┘ └────────┘ └┬────────┘ └────────────┘
                                        │ amqp
                          ┌─────────────▼──────────────┐
                          │         WORKER             │
                          │ consumer · executor ·      │
                          │ converters · pipelines ·   │
                          │ model_registry · models    │
                          └─────────────┬──────────────┘
                                        │
                          ┌─────────────▼──────────────┐
                          │        SCHEDULER           │
                          │ cleanup · retry_jobs ·     │
                          │ metrics                    │
                          └────────────────────────────┘

   Observability (all nodes): OTel SDK ─▶ otel-collector ─▶ Prometheus/Grafana
   Delivery: GitHub Actions ─▶ lint · type · test · security ─▶ build ─▶ deploy
```

## Components

### Gateway (FastAPI — `gateway/`)

HTTP-facing modular monolith. Exposes `/api/v1/*` (envelope), `/health/live`,
`/health/ready`, and Prometheus `/metrics`.

- **domains** — `auth`, `users`, `scans`, `jobs`, `audit`, `notification` (placeholder), `report` (placeholder)
- **repositories** — user, credential, organization, scan, object, job, audit, model
- **core** — config, feature_flags, db, redis, storage (provider abstraction), security, queue, rate_limit, otel, deps, logging

Call chain: `Router → Service → Repository → SQLAlchemy`. Business logic never
touches the ORM directly.

### PostgreSQL (metadata — source of truth)

9 tables: organizations, users, credentials, scans, scan_outputs, objects,
model_versions, jobs, audit_logs. See [`../database/er.md`](../database/er.md).
All image bytes live in object storage; the database stores metadata + object
keys only.

### Redis (cache + rate limiting — never authoritative)

- Endpoint rate limits (login 5/min/IP, register 3/day/IP, upload 20/h/user, download 300/h/user)
- Session blacklist (revoked JWT `jti`s)
- Scan-status cache (short TTL, fallback to PostgreSQL)

If Redis crashes, nothing breaks. If PostgreSQL crashes, everything stops.

### RabbitMQ (async jobs + events)

Two topic exchanges:

```
commands        events
├── inference.run       ├── scan.completed
├── cleanup.run         ├── scan.failed
└── notification.send   └── user.created
                        └── report.generated
```

Workers consume from `commands`; anything that wants to react (notifications,
analytics, billing, report generation) subscribes to `events` — no changes to
inference code.

### Worker (isolated inference process — `worker/`)

Subscribes to `inference.run`. Downloads the original object, converts to a
**CommonImage** (pipeline never sees source format), runs
`preprocess → infer → postprocess`, uploads outputs, writes
`model_versions` + scan/output rows, publishes `scan.completed`/`scan.failed`.

Imports only from `gateway.core`, `gateway.models`, `gateway.schemas` — never
from `gateway.domains`. This is the seam for extracting it into a GPU pod.

### Scheduler (`scheduler/`)

Long-running process (compose service with its own image + heartbeat
healthcheck, ADR-009). Every `scheduler_poll_interval_seconds` it runs a retry
pass: re-issue due `RETRYING` jobs, recover stalled `RUNNING` jobs, and
re-issue unconfirmed `QUEUED` republishes — each claimed atomically so
multiple scheduler instances never double-publish. Cleanup (soft-delete purge
+ object lifecycle) runs via the internal timer and on demand through the
`cleanup.run` command consumer; both share one
`CleanupService.run_cleanup` implementation guarded by a Redis distributed
lock. Future CronJob / EventBridge triggers can drive the same pass without
changing cleanup logic.

### Object storage (MinIO locally, S3 in prod)

Private bucket, server-side encryption (SSE-KMS; MinIO SSE locally). Images
served exclusively via short-lived presigned URLs.

## Primary data flow — scan denoise

```
1. POST /api/v1/scans        (JWT, rate-limited, validated)
2. Gateway ──▶ MinIO          upload original (StorageProvider.upload)
3. Gateway ──▶ PostgreSQL     scans + objects + scan_outputs + jobs (QUEUED)
4. Gateway ──▶ RabbitMQ       publish inference.run (W3C trace headers)
5. Worker  ◀─▶ RabbitMQ       consume → RUNNING
6. Worker  ◀─▶ MinIO          download original
7. Worker                    converters → CommonImage → pipeline
8. Worker  ──▶ MinIO          upload 4 outputs
9. Worker  ──▶ PostgreSQL     scan/outputs/model_versions/jobs (COMPLETED)
10. Worker ──▶ RabbitMQ       publish scan.completed (event)
11. Gateway                  reads PG (truth) → caches status in Redis
12. Client                   polls GET /api/v1/scans/{id}
13. Client ──▶ Gateway        GET .../output/{type}/url → audit DOWNLOAD → presign
14. Browser ◀──▶ MinIO        direct download (no proxy, no backend bandwidth)
```

## Observability

- W3C TraceContext propagates across RabbitMQ message headers and DB writes.
- `trace_id` is persisted on `jobs` and `audit_logs` and returned in every envelope.
- `X-Request-ID` (edge) is bridged to `trace_id` in the gateway.
- Traces → OTLP → otel-collector → Jaeger/Grafana Tempo (added later, zero app change).
- `/metrics` → Prometheus → Grafana dashboards.

## Deployment topology (Docker now → K8s later)

- **Docker Compose (dev):** postgres, redis, rabbitmq, minio, otel-collector, prometheus, grafana + gateway, worker, scheduler images.
- **K8s (later):** gateway Deployment (horizontal), worker as a separate Deployment/StatefulSet scaled independently (GPU node pool), scheduler as CronJobs, probes via `/health/live` + `/health/ready`.
- **Terraform (later):** AWS account wiring — RDS, ElastiCache, MQ, S3 + KMS, EKS.

See [`../api/openapi.yaml`](../api/openapi.yaml) for the HTTP contract and
[`../security/threat-model.md`](../security/threat-model.md) for trust boundaries.

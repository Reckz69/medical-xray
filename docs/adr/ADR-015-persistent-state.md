# ADR-015: Persistent State Strategy

- **Status:** Accepted
- **Date:** 2026-08-08
- **Deciders:** Architecture review (Sprint 4D)
- **Related:** [ADR-012](ADR-012-deployment-architecture.md), [ADR-013](ADR-013-https-ingress.md), [ADR-014](ADR-014-secrets-management.md), [ADR-003](ADR-003-presigned-urls.md), [ADR-004](ADR-004-server-side-encryption.md)

## Context

Four services hold state:

| Service | State | Current dev persistence |
| --- | --- | --- |
| PostgreSQL | Jobs, scans, users, schema via Alembic | `postgres_data` volume |
| Redis | Rate-limit counters, cleanup locks | `redis_data` volume |
| RabbitMQ | Durable job queue | `rabbitmq_data` volume |
| MinIO | Uploaded scans + outputs (S3 API) | `minio_data` volume |

The application is storage-agnostic at two seams: `DATABASE_URL` (asyncpg) and
`STORAGE_PROVIDER` (`minio`/`s3`, already switchable via env, with presigned
URLs and server-side encryption per ADR-003/ADR-004). The decision is how each
is run in production and how it is protected.

## Decision

### Self-hosted in containers, with volumes, as the default

On the canonical single-VM deployment (ADR-012), all four services run as
containers with Docker named volumes on the VM's disk:

- `postgres_data` — Postgres data directory.
- `redis_data` — Redis RDB persistence.
- `rabbitmq_data` — queue definitions and durable messages.
- `minio_data` — object store data.

Volumes, not bind mounts, so the host filesystem layout is managed by Docker.
Backups operate at the service level (see below), not by copying the volume
directory directly.

### Object store seam: MinIO ↔ S3

The application already selects the store via `STORAGE_PROVIDER`:
- **MinIO container (default):** the tested path, no external dependency.
- **S3-compatible managed object storage:** set `STORAGE_PROVIDER=s3`,
  `S3_ENDPOINT`, and credentials; presigned URLs and server-side encryption
  (ADR-003/004) are preserved because they are app-level, provider-agnostic.

This means the object layer can move to a managed bucket without any app
change — the largest single piece of state is the easiest to externalize.

### Backup strategy (detailed runbooks in Phase 5)

- **PostgreSQL:** nightly logical backup via `pg_dump` (running in a one-shot
  container on the same network), kept on the VM plus off-site; WAL archiving
  is the follow-on for point-in-time recovery. Restore runbook tested in Phase
  5.
- **MinIO/S3:** `mc mirror` for the MinIO path; native bucket replication/lifecycle
  for S3. The existing lifecycle knobs (`OBJECT_ARCHIVE_DAYS=30`,
  `OBJECT_DELETE_DAYS=365`) are wired to the object lifecycle rules in Phase 5.
- **RabbitMQ:** definitions export (`rabbitmqadmin export`); queues are
  effectively a replayable work log, so data loss is limited to in-flight
  messages. Documented trade-off.
- **Redis:** RDB snapshots on the volume; acceptable loss window sized to the
  Redis cache/counter use.

Targets: **RPO ≤ 24 h** (nightly logical backups) and **RTO ≤ 4 h** (restore
from backup on the VM), documented in `docs/engineering/backup-restore.md`.

### Managed services as the documented alternative

For a deployment that prefers managed infrastructure, the alternative topology
(reference only, not the default) is:

- Postgres → **RDS** (or Cloud SQL): `DATABASE_URL` changes, schema/Alembic
  unchanged.
- Redis → **ElastiCache** (or Memorystore): `REDIS_URL` changes.
- RabbitMQ → **Amazon MQ** (or a managed queue): `RABBITMQ_URL` changes.
- MinIO → **S3**: `STORAGE_PROVIDER=s3` + endpoint change.
- Kubernetes alternative: the four services as StatefulSets/Deployments with
  PVCs (see `deploy/k8s/`).

The env seams make every one of these a config change, not a code change. The
Terraform outline (ADR-012, `deploy/terraform/`) documents the managed path
for a later infrastructure automation sprint.

## Alternatives considered

- **Managed everything as the default** — rejected (ADR-012). Monthly cost and
  vendor lock-in are not justified at this scale; self-hosted is the tested
  path.
- **Host bind mounts instead of volumes** — rejected. Volumes keep Docker in
  charge of layout, permissions, and lifecycle; bind mounts invite host/path
  drift.
- **MinIO in replicated/distributed mode** — rejected for now. Single-node
  MinIO matches single-VM availability; erasure coding adds nodes and
  complexity without an availability requirement yet. Documented as the
  scale-out step.

## Consequences

**Positive**
- The default deployment is exactly what CI tests, with app-level seams
  (`DATABASE_URL`, `STORAGE_PROVIDER`) ready for managed swap.
- Backups and restore are defined per service, with explicit RPO/RTO.
- Object state (the bulk) is the easiest to externalize.

**Negative**
- Self-hosted state is the operator's responsibility: patching, backups, and
  disk space are on the VM owner.
- Single VM = single point of failure for all four state services; no HA until
  the managed or Kubernetes path is taken.
- RabbitMQ and Redis persistence are best-effort by design; the docs must state
  their loss windows honestly.

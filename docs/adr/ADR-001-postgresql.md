# ADR-001: PostgreSQL over MongoDB for metadata

- **Status:** Accepted
- **Date:** 2026-07-31
- **Deciders:** Architecture review
- **Related:** [ADR-004](ADR-004-server-side-encryption.md), [er.md](../database/er.md)

## Context

The platform stores scan metadata (ownership, status, noise variance, routing
message, job state, audit trail) alongside X-ray images. An earlier draft used
MongoDB; the review settled on relational metadata.

## Decision

Use PostgreSQL as the single source of truth for all metadata. Images stay in
object storage (MinIO/S3), not in the database.

## Rationale

- Data is naturally relational and transactional: scans, outputs, jobs, objects,
  organizations, audit — with strong integrity and referential guarantees.
- Audit trails and lifecycle transitions (QUEUED→RUNNING→COMPLETED) benefit from
  ACID transactions and unique constraints (e.g. one output per type per scan).
- SQL queries for reporting/analytics (per-org usage, scan counts) are trivial.
- Rich type support: `uuid`, `citext`, `inet`, `jsonb`, `timestamptz` cover every need.
- Async driver (`asyncpg` via SQLAlchemy) fits the FastAPI async model.

## Consequences

**Positive**
- Strong schema, foreign keys, migrations via Alembic.
- Retry/lifecycle correctness from transactions and constraints.
- Multi-tenant org scoping is a simple indexed FK.

**Negative**
- Schema changes need migrations (a feature here, not a tax — discipline).
- Document-style flexibility (MongoDB's strength) is not needed for this data.

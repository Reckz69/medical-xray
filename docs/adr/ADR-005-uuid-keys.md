# ADR-005: UUID primary keys everywhere

- **Status:** Accepted
- **Date:** 2026-07-31
- **Deciders:** Architecture review
- **Related:** [er.md](../database/er.md)

## Context

Every table needs a primary key. The default habit is `BIGSERIAL`/`IDENTITY`
auto-increment integers.

## Decision

All primary keys are `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
(PostgreSQL 13+). No auto-increment integer keys anywhere.

## Rationale

- **Non-enumerable resource IDs** — `POST /api/v1/scans` returns a UUID, not a
  guessable `7`. This is defense-in-depth against IDOR (never the only control —
  ownership checks remain mandatory).
- **Client-generated keys** possible — enables offline/idempotent creation and
  simpler eventual event correlation (`scan_id` known before insert).
- **Distributed-friendly** — UUIDs work across shards, replicas, and future
  event-driven systems with no coordination; safe if the gateway ever splits.
- **Merge-friendly** — no collision risk when migrating/splitting data.

## Consequences

**Positive**
- Uniform key convention; the `er.md` schema stays consistent.
- Security + distributed-readiness for free.

**Negative**
- 16-byte keys with a slightly larger index footprint than `bigint` (irrelevant
  at this data volume).
- No natural sort order; order by `created_at` where needed (already indexed).

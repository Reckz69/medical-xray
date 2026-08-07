# ADR-009: Distributed scheduler for retry, stall recovery, and cleanup

- **Status:** Accepted
- **Date:** 2026-08-07
- **Deciders:** Architecture review
- **Related:** [ADR-002-rabbitmq.md](ADR-002-rabbitmq.md), [ADR-008-orchestrator.md](ADR-008-orchestrator.md)

## Context

Sprint 2B left the worker as a single long-running consumer with no recovery
story: a worker that dies mid-job leaves the job stuck in `RUNNING`, a published
`inference.run` that is lost leaves a `QUEUED` job that never runs, and a
retryable failure that exhausts its attempts stays `RETRYING` forever. Soft-
deleted scans also accumulate until a human purges them. Each of these needs a
periodic, out-of-band pass that the async message flow alone cannot provide.

There is also a deployment concern: the gateway and worker already run as
first-class compose services, but any new process must be containerized,
health-checked, and restartable the same way.

## Decision

Add a dedicated `scheduler/` process that runs timed recovery passes and is
triggerable by commands. Concretely:

1. **Retry pass** (every `scheduler_poll_interval_seconds`): re-issue
   `inference.run` for due `RETRYING` jobs (backoff elapsed), move them back to
   `QUEUED`, and stamp a republish marker so the pass is idempotent.
2. **Stall recovery** (same cadence): jobs stuck in `RUNNING` past
   `job_stall_timeout_seconds` are pushed through the retry pipeline, or fail
   terminally (with a `scan.failed` event) at the attempt cap.
3. **Unconfirmed recovery**: `QUEUED` jobs whose republish marker is older than
   the grace window are re-issued (scheduler-crash safety).
4. **Cleanup** (every `scheduler_cleanup_interval_seconds` via the internal
   timer, and on demand via the `cleanup.run` command): soft-deleted scans past
   `scan_purge_days` are purged (rows + S3 objects, batch-limited).

All retry/republish work is claimed atomically with a DB
`attempted_recovery_at` marker so two scheduler instances never double-publish.
The cleanup pass is guarded by a Redis distributed lock (`SET NX PX` with a
compare-and-delete Lua release) and records duration/deleted/archived/failure/
skipped metrics. Every trigger source is logged and carried in the run report
(`source=timer` vs `source=cleanup.run`).

### Single cleanup implementation

`CleanupService.run_cleanup(source=...)` is the **only** entry point for a
cleanup pass. Both triggers call it:

- the scheduler's internal timer — the production default, and
- the `cleanup.run` command consumer — the operational interface for manual or
  scheduled cleanup requests.

The scheduler binds a durable `scheduler.cleanup` queue to the `commands`
exchange routing key `cleanup.run` and consumes it with prefetch 1. A future
CronJob, Kubernetes CronJob, or EventBridge rule can publish `cleanup.run`
(or replace the timer) **without changing the cleanup logic** — the lock makes
concurrent trigger sources safe.

### Deployment

The scheduler is a first-class compose service (own `scheduler/Dockerfile`,
`restart: unless-stopped`, `depends_on` healthy infra). Its healthcheck
(`scheduler/healthcheck.py`) exits non-zero when the heartbeat file stamped each
cycle goes stale, so a stalled loop restarts instead of silently idling. The
gateway joins compose the same way, applying migrations on start
(`alembic upgrade head`).

## Rationale

- A periodic process is the only way to observe and repair the durable side
  effects (`RUNNING`/`RETRYING`/`QUEUED` rows) that the event flow leaves
  behind — exactly what a job-retry system needs.
- A dedicated scheduler (rather than embedding recovery in the worker) keeps the
  worker strictly consumer→pipeline→persist and lets recovery scale/replace
  independently of inference.
- The DB claim marker makes the scheduler horizontally safe; the Redis lock
  makes cleanup horizontally safe; both are cheap and idempotent.
- Durable command queue (`cleanup.run`) over a timer-only design means
  operators and future schedulers can trigger cleanup deterministically, and the
  timer stays replaceable.

## Alternatives considered

- **Recovery inside the worker** — couples repair with inference; a dead worker
  can't repair itself anyway.
- **Postgres `pg_cron` / SQL-only passes** — no metrics, no S3 object cleanup,
  no command interface, harder to health-check; keeps business logic out of SQL.
- **Kubernetes CronJob from day one** — heavier than the current compose stack
  needs; the command queue and single-implementation cleanup keep the door open
  without changing code.
- **Timer-only cleanup (no `cleanup.run`)** — no operational/manual trigger and
  no clean seam for future schedulers; rejected in review.

## Consequences

**Positive**
- Stuck/lost jobs self-heal within one poll interval; retryable failures are
  re-issued on backoff and fail terminally at the attempt cap.
- Soft-deleted scans are purged on a retention schedule, batch-limited and safe
  against concurrent runs.
- Scheduler and gateway are containerized with healthchecks and restart
  policies; the full stack runs with one compose command.
- Cleanup logic lives in exactly one place; future scheduler triggers slot in
  via `cleanup.run` or by replacing the timer.

**Negative**
- New long-running process to operate and monitor (heartbeat healthcheck,
  restart policy).
- Integration tests must not run while the worker/scheduler are up (shared dev
  queue); compose header documents `docker compose stop worker scheduler gateway`
  before pytest.
- Distributed-lock correctness now depends on Redis availability; a Redis
  failure skips a cleanup run rather than risking a concurrent purge.

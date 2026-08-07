# Backup & Restore

> Sprint 4D (ADR-015). Self-hosted state services on the canonical single-VM
> deployment. Targets: **RPO ≤ 24 h** (nightly logical backups), **RTO ≤ 4 h**
> (restore from backup on the VM). Managed alternatives (RDS/S3/etc.) inherit
> their provider's backup story — see ADR-015.

```mermaid
flowchart LR
    PG[(Postgres)] -->|nightly pg_dump| B1[backup .sql.gz]
    B1 -->|off-site copy| OS[(object store / second host)]

    M[(MinIO)] -->|mc mirror| B2[backup mirror]
    B2 -->|off-site copy| OS

    Q[(RabbitMQ)] -->|definitions export| B3[definitions.json]
    R[(Redis)] -->|RDB snapshot on volume| B4[redis_data volume]

    RESTORE[Restore runbook] --> PG
    RESTORE --> M
    RESTORE --> Q
    RESTORE --> R
```

## What to back up

| Service | Method | Granularity | What's lost without it |
| --- | --- | --- | --- |
| PostgreSQL | `pg_dump` (logical), nightly; WAL archiving = follow-on for PITR | schema + data | **everything** — users, jobs, scans |
| MinIO / S3 | `mc mirror` nightly (or bucket replication on managed S3) | objects | uploaded scans + outputs |
| RabbitMQ | `rabbitmqadmin export` (definitions) | topology | durable queue + exchange definitions |
| Redis | RDB snapshot on its volume (already on by default) | cache/counters | rate-limit state, cleanup locks (recomputable) |

## Nightly backup (single VM)

Postgres dump via a one-shot container on the compose network:

```sh
cd deploy/production
docker compose exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc \
  | gzip > "/var/backups/denoise/$(date +%F).sql.gz"
```

MinIO mirror (uses the `mc` CLI from the `minio-init` service — same compose
network, no hardcoded network name). `-e VAR` passes the `.env` value through.
Set `BACKUP_ACCESS_KEY` / `BACKUP_SECRET_KEY` in `.env` (or export them) to the
**off-site** endpoint of your choice — a backup on the same VM is not a backup:

```sh
cd deploy/production
docker compose run --rm --no-deps \
  -e MINIO_ROOT_USER -e MINIO_ROOT_PASSWORD -e S3_BUCKET \
  -e BACKUP_ACCESS_KEY -e BACKUP_SECRET_KEY \
  minio-init sh -c '
    mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
    mc alias set backup https://s3.example.com "$BACKUP_ACCESS_KEY" "$BACKUP_SECRET_KEY"
    mc mirror --overwrite local/$S3_BUCKET backup/$S3_BUCKET
  '
```

RabbitMQ definitions:

```sh
docker compose exec rabbitmq rabbitmqadmin export /tmp/definitions.json
```

Schedule all three as a systemd timer / cron (`@daily`), then **copy the
`.sql.gz` and the mirror off-site** (object storage on a second host, or a
different region). A backup that lives on the same VM is not a backup.

## Object lifecycle (ADR-015 / ADR-003)

The app already exposes `OBJECT_ARCHIVE_DAYS=30` and `OBJECT_DELETE_DAYS=365`
knobs. Wire them to the object store lifecycle so old scans are archived then
deleted (scheduler cleanup purges DB rows; lifecycle rules cover the objects):

- **MinIO:** an idle/ILM rule on `denoise-xray` — transition to a colder tier
  after `OBJECT_ARCHIVE_DAYS`, expire after `OBJECT_DELETE_DAYS`.
- **Managed S3:** a bucket lifecycle rule with the same two transitions.

## Restore runbook (target ≤ 4 h)

1. **Provision/repair the VM** and bring up `postgres`, `redis`, `rabbitmq`,
   `minio` from `deploy/production/docker-compose.yml` (infra-only is fine).
2. **Postgres:** drop and recreate the schema, then load the nightly dump:
   ```sh
   docker compose exec -T postgres \
     sh -c 'gunzip -c /var/backups/denoise/YYYY-MM-DD.sql.gz \
       | pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists'
   ```
3. **RabbitMQ:** `rabbitmqadmin import` the definitions export; queued work is
   re-published by clients/retry on the next cycle.
4. **MinIO/S3:** `mc mirror` back from the backup location (or rely on bucket
   replication for the managed path). The app's `STORAGE_PROVIDER` seam
   (ADR-015) means the object layer can be restored to S3 even if it was MinIO.
5. **Redis:** empty is acceptable (counters reset, locks expire); restore the
   RDB only if desired.
6. **Bring the app up** and verify:
   ```sh
   docker compose up -d
   curl -sf https://api.<SITE_DOMAIN>/health/ready
   ```
7. **Test the restore** quarterly — a backup that has never been restored is
   a guess.

## Notes & limits

- `pg_dump -Fc` gives a logical backup; **WAL archiving for point-in-time
  recovery is a documented follow-on**, not yet configured (RPO ≤ 24 h is met
  by the nightly dump).
- Redis and RabbitMQ loss windows are best-effort by design (ADR-015); the
  durable sources of truth are Postgres and the object store.

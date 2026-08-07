# Sprint 4D — Phase 5 Review: Operations docs, validation, finalize

- **Status:** Review-complete, ready to tag `sprint-4d` and push
- **Date:** 2026-08-08
- **Branch:** `main`
- **Related:** [ADR-012](../adr/ADR-012-deployment-architecture.md) … [ADR-017](../adr/ADR-017-versioning-release.md), `docs/engineering/ci.md`, `docs/engineering/deployment.md`, `docs/engineering/backup-restore.md`, `docs/engineering/secret-rotation.md`, `docs/engineering/production-checklist.md`, `docs/reviews/sprint-4d-phase4-review.md`

## Goal

Close out Sprint 4D with the operations runbooks and final validation: backups,
restore, secret rotation, and a decision-forcing production checklist, all kept
consistent with the CI image publishing (ADR-016/017) and the docs index
(README + CHANGELOG). Then tag `sprint-4d` and push.

## Delivered

### `docs/engineering/ci.md` — synced with `ci-images.yml`

- Overview ASCII now shows `ci-images.yml` (publish) alongside
  `ci.yml`/`ci-full.yml` + benchmark.
- Trigger table: push `main` → `ci-full.yml` + `ci-images.yml`; `v*` /
  `sprint-*` tags and `workflow_dispatch` → `ci-images.yml`;
  `concurrency: cancel-in-progress` noted on all three.
- Required secrets still **none**; `GITHUB_TOKEN` built-in; `ci-images.yml`
  adds `permissions: packages: write`; GHCR pull needs only a deploy-time
  `docker login ghcr.io` (ADR-014).
- "Image publishing (ADR-016/017)": 4-tag table (`latest`, `<sha>`,
  `v<semver>`, `<sprint-tag>`) + `github.repository_owner` user-namespace note.
- Cache table: Buildx `type=gha` per service (`images-<service>`); durable
  artifact = the published GHCR images.

### `docs/engineering/backup-restore.md` (new)

- Mermaid backup flow; per-service table: Postgres `pg_dump` nightly logical,
  MinIO `mc mirror`, RabbitMQ `rabbitmqadmin export` definitions, Redis RDB on
  volume (best-effort, ADR-015).
- Concrete commands (`pg_dump | gzip`, one-shot `mc mirror` container,
  definitions export) + systemd-timer/cron schedule + **off-site copy
  requirement**.
- `OBJECT_ARCHIVE_DAYS=30` / `OBJECT_DELETE_DAYS=365` wired to MinIO ILM / S3
  lifecycle.
- Numbered restore runbook targeting **RTO ≤ 4 h** (`pg_restore --clean
  --if-exists`, definitions import, object mirror-back, Redis acceptable-empty,
  app bring-up + `/health/ready` verify), plus quarterly restore test.
- WAL/PITR documented as a follow-on, not configured.

### `docs/engineering/secret-rotation.md` (new)

- Manual rotation on the VM; preconditions incl. recording new+old values first.
- Runbooks: JWT (`openssl rand -hex 32`, gateway recreate, sign-out window),
  PostgreSQL (`ALTER USER` + `.env` + `--force-recreate` app services),
  RabbitMQ (`rabbitmqctl change_password`), MinIO (`MINIO_ROOT_PASSWORD` +
  `S3_SECRET_KEY`, recreate minio + apps), Grafana overlay, GHCR PAT.
- Post-rotation checks: `docker compose config`, `ps`, health smoke.

### `docs/engineering/production-checklist.md` (new)

- 8 sections: Edge & TLS, Secrets & identity, Hardening, Resource & runtime,
  Data & durability, Monitoring & alerting, Operational practice.
- Every checkbox is a decision: unchecked = explicit accepted risk.
- SR-1..5 coverage table with statuses; SR-3 (non-root/read-only/pinned tags)
  and SR-5 (SAST/SCA) are **recorded current gaps**, flagged required-before-
  traffic.

### `docs/engineering/deployment.md` — HTTPS/ingress sequence diagram

- Mermaid: browser → DNS → Caddy `:443` (Let's Encrypt auto-renew) →
  `gateway:8000` plain HTTP internal; frontend via Vercel (alt: containerized,
  `FRONTEND_UPSTREAM`). Consistent with ADR-013.

### Docs sync

- `docs/README.md` index: engineering table now lists deployment, scaling,
  backup-restore, secret-rotation, production-checklist; `ci.md` row updated.
- `docs/CHANGELOG.md`: "Sprint 4D" entry (Added/Changed/Known gaps), newest
  first.

## Decisions

1. **Ops docs are runnable, not aspirational** — every command was cross-checked
   against the actual compose file, `generate-secrets.sh`, and `.env.example`;
   nothing references a service, volume, or variable that does not exist.
2. **Durable sources of truth are Postgres + object store** — Redis/RabbitMQ
   loss is best-effort by design (ADR-015); the backup doc says so explicitly
   rather than pretending full fidelity.
3. **A same-VM copy is not a backup** — off-site copy is a stated requirement,
   and restore is a tested runbook (quarterly), not a hope.
4. **Checklist is decision-forcing** — SR-3/SR-5 gaps are labeled in the
   checklist and in the CHANGELOG "Known gaps" section so they cannot be
   silently merged away.
5. **`latest` is a moving tag** — the checklist and `ci.md` both tell operators
   to pin `<sha>` / `v<semver>` / `<sprint-tag>` for upgrades (ADR-017).

## Validation

- `actionlint` on `ci.yml`, `ci-full.yml`, `ci-images.yml` — **0 errors**.
- `docker compose config -q` on `deploy/production/docker-compose.yml`:
  - without `.env` → fails on `${SITE_DOMAIN:?}` etc. (**expected**,
    secrets-gated design), exit 1;
  - with a generated `.env` → **OK**;
  - with `-f observability.yml` overlay → **OK**. Temp `.env` removed after.
- All 8 `deploy/k8s/*.yaml` parse via `yaml.safe_load_all` (container run) — OK.
- Markdown link scan over `docs/**/*.md` — **0 broken links**.
- Weights path cross-check: `.env.example`, compose, and ops docs all resolve to
  `/weights/n2n_unet_best_weights04.keras` (model in-repo path,
  `MODEL_WEIGHTS_PATH` host bind `:ro`) — consistent with ADR-011.

## Remaining

- Tag `sprint-4d`, push `main` + tag to `denoisex`.
- Sprint 4E (future, IaC-only): choose cloud, replace the Terraform scaffold
  with a deployable configuration, remote state + locking.

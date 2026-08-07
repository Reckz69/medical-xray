# Sprint 4D — Phase 2 Review: production Compose, Caddy, secrets

- **Status:** Review-complete, ready to commit
- **Date:** 2026-08-08
- **Branch:** `main`
- **Related:** [ADR-012](../adr/ADR-012-deployment-architecture.md), [ADR-013](../adr/ADR-013-https-ingress.md), [ADR-014](../adr/ADR-014-secrets-management.md), [ADR-015](../adr/ADR-015-persistent-state.md), `docs/reviews/sprint-4d-phase1-review.md`

## Goal

Turn the ADR-012 architecture into a usable production compose stack with
Caddy TLS at the edge, generated (never committed) secrets, and a runbook that
covers both supported deployment modes — usable *before* the GHCR registry
exists, and switchable to it afterward (Phase 3).

## Delivered

- **`deploy/production/docker-compose.yml`** — production stack: Caddy (TLS
  edge), gateway/worker/scheduler, postgres/redis/rabbitmq/minio (+`minio-init`),
  and named volumes (incl. `caddy_data`). Differences from the dev file:
  no host-published infra ports, resource limits, secrets as `${VAR:?}` (a
  missing/empty secret **fails `docker compose config`** — no silent insecure
  default), `env_file: .env` + internal-wiring overrides, weights mounted `:ro`,
  MinIO without a healthcheck (no `curl` in the image → `service_started`).
- **`deploy/production/Caddyfile`** — `api.<SITE_DOMAIN>` → `gateway:8000`;
  `<SITE_DOMAIN>` frontend route enabled only when `FRONTEND_UPSTREAM` is set
  (default: frontend on Vercel at its own record). ACME email from env.
- **`deploy/production/.env.example`** — full production template with
  `__generate__` placeholders; every secret documented (ADR-014).
- **`deploy/production/generate-secrets.sh`** — creates `.env` from
  `.env.example`, `openssl rand` credentials, `chmod 600`, refuses to
  overwrite, prints credentials once. S3 keys mirror the MinIO root creds.
- **`deploy/production/observability.yml`** — removable production overlay
  (OTel/Prometheus/Grafana), preserving the ADR-010 invariant; scrape config
  reuses `backend/infrastructure/...` unchanged.
- **`docs/engineering/deployment.md`** — topology (mermaid), the **two
  supported deployment modes** (`build` = dev/first deploy, `pull` = CI
  artifacts), first-deploy provisioning, ports matrix, upgrade/rollback with
  the ADR-017 ordering rule, pointers to backup/rotation/checklist.

## Decisions

1. **Both `image:` and `build:` are present per service.** `build` tags as
   `image`; `pull` fetches it. The file is registry-agnostic and the two
   documented modes are a single command choice — exactly the ADR-012/016 seam.
2. **No host-published ports except Caddy `:80/:443`.** Infra and app services
   are internal-only (ADR-013); observability is reached via SSH tunnel.
3. **Secrets are `${VAR:?}` in compose, not defaults.** Compose interpolation
   substitutes a *blank* string for an unset var (not an error), so the plain
   `${VAR}` form would silently ship an empty credential; `${VAR:?}` turns a
   missing secret into a hard `docker compose config` failure (ADR-014).
4. **Frontend stays out of the compose file.** No frontend image exists;
   Vercel/Next-standalone is the documented default (ADR-016), and the Caddy
   frontend route is inert unless `FRONTEND_UPSTREAM` is set.

## Validation

- `docker compose -f docker-compose.yml config` with a generated `.env` → exit 0.
- `docker compose -f docker-compose.yml -f observability.yml config` → exit 0.
- Without `.env`: `docker compose config` → exit 1 (loud failure).
- `generate-secrets.sh` (temp-dir test): no `__generate__` values left (only a
  comment mentions the placeholder), `.env` perms `-rw-------`, second run
  refuses, `S3_ACCESS_KEY` == `MINIO_ROOT_USER`.
- `caddy validate` (caddy:2.9-alpine) → **"Valid configuration"**.
- `docker compose config --services` = postgres rabbitmq redis minio scheduler
  worker gateway caddy minio-init (observability overlay adds the three).

## Remaining

- Phase 3 (GHCR `ci-images.yml`) publishes the images the `image:` seam
  references; Phase 4 (k8s/terraform reference) maps this topology; Phase 5
  (operations, review docs, tag).
- Non-root / read-only-root / pinned-deps hardening (SR-3) is flagged in the
  compose header and the future checklist — the images must change first.

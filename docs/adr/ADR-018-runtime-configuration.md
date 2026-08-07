# ADR-018: Runtime Configuration — one compose stack for every environment

- **Status:** Accepted
- **Date:** 2026-08-08
- **Deciders:** Architecture review (Sprint 4E)
- **Related:** [ADR-012](ADR-012-deployment-architecture.md), [ADR-013](ADR-013-https-ingress.md), `deploy/production/.env.example`, `deploy/production/docker-compose.yml`

## Context

The production compose stack is meant to run identically in two very different
places: a developer's laptop (Docker Desktop, no DNS, no public IP) and a
production Linux VM (public DNS records, Let's Encrypt). The first natural
instinct is to branch the code — `if ENVIRONMENT == "local"` blocks, a second
compose file, a second `Caddyfile` checked in under a different name, separate
frontend and backend build paths.

Branches are how drift and untestable configuration creep in: the "local" path
drifts from the "prod" path until nobody can prove the prod path ever ran.

## Decision

**There is exactly one production compose stack, and `.env` is the only
thing that changes between environments.** No `LOCAL`/`CLOUD` branches in
application code. The same `docker-compose.yml`, the same Caddyfiles, the same
frontend image, the same weights mount, the same observability overlay — the
environment merely selects values.

The runtime-configuration knobs and what each one changes:

| Knob | Local (default) | Cloud | Effect |
| --- | --- | --- | --- |
| `SITE_DOMAIN` | `localhost` | `denoise-x.example.com` | Names every edge site: `api.<SITE_DOMAIN>`, `s3.<SITE_DOMAIN>`, `<SITE_DOMAIN>` |
| `CADDYFILE` | `Caddyfile.local` | `Caddyfile` | Selects the edge config (local CA vs Let's Encrypt, ADR-013) |
| `COMPOSE_PROFILES` | `frontend` | empty | Whether the containerized frontend is included (empty → Vercel, ADR-016) |
| `CORS_ORIGINS` | `["https://localhost"]` | `["https://app.<SITE_DOMAIN>"]` | Gateway CORS allow-list |
| `S3_PUBLIC_ENDPOINT` | `https://s3.localhost` | `https://s3.<SITE_DOMAIN>` | Browser-reachable origin for presigned URLs (ADR-003) |
| `MODEL_WEIGHTS_PATH` | `../../n2n_unet_best_weights04.keras` | `/opt/denoise/...` | Host path mounted `:ro` into the worker (ADR-011) |
| `ACME_EMAIL` | empty | `ops@example.com` | Let's Encrypt account (cloud only) |

A clean clone is therefore runnable end-to-end with zero edits: copy
`.env.example` → `.env`, run `./generate-secrets.sh`, place the weights at the
repo root, `docker compose up -d --build`. The same stack, lifted to a VM with
DNS records and a few `.env` values changed, is the production deployment.

## Key mechanisms

- **`CADDYFILE` mounts the edge config** (`./${CADDYFILE:-Caddyfile}` →
  `/etc/caddy/Caddyfile`). The two files are structurally identical — both
  define `api.`, `s3.`, and bare `<SITE_DOMAIN>` sites — and differ only in
  TLS: `Caddyfile.local` sets `local_certs` + `email off` (Caddy internal CA),
  `Caddyfile` relies on ACME. Caddy's local CA issues self-signed certs, so
  browsers/curl need a one-time trust step in local mode.
- **`S3_PUBLIC_ENDPOINT` drives presigned download URLs** (ADR-003): the app
  talks to `S3_ENDPOINT` (internal `http://minio:9000`) for object I/O, but
  builds presigned GET URLs against the browser-reachable public origin. Caddy
  serves `s3.<SITE_DOMAIN>` → `minio:9000` **without gzip** (S3 objects must be
  served verbatim). MinIO's SDK rejects path-style endpoints, hence the
  subdomain. Empty value → presign against `S3_ENDPOINT` (internal/tooling only).
- **`COMPOSE_PROFILES` gates the frontend**: in local mode the profile brings
  the containerized Next.js standalone frontend up; in cloud mode the profile
  is empty and the frontend lives on Vercel. Caddy's `<SITE_DOMAIN>` site
  reverse-proxies `FRONTEND_UPSTREAM` when set, so the same edge serves the
  containerized frontend when present.

## Alternatives considered

- **A `LOCAL`/`CLOUD` branch in app config** — rejected. Two paths to test, two
  paths to drift; the local path would silently stop matching prod.
- **Two compose files** (`docker-compose.local.yml` + `docker-compose.yml`) —
  rejected. The observability overlay already composes; multiplying the matrix
  makes "what actually ran in prod" unprovable.
- **Separate `frontend` build for Vercel vs container** — rejected. The same
  standalone build (`output: "standalone"`) runs in both; only the serving
  surface differs (Vercel edge vs Caddy → frontend:3000).

## Consequences

**Positive**
- One stack is proven by running it: every local deployment *is* the prod
  deployment, so the DoD "clean clone → compose up → E2E" gate genuinely
  validates the production topology.
- Switching environments is a `.env` edit, not a code change; nothing in the
  codebase reads `ENVIRONMENT == "local"` to behave differently.

**Negative**
- Local mode is self-signed (Caddy internal CA): tools must trust the local
  root CA or use `-k`; that cost is confined to local dev.
- Cloud mode still needs real DNS (`api.` and `s3.` A records) before first
  boot — unchanged from ADR-013/ADR-003.
- The `s3.` subdomain is mandatory for presigned downloads (SDK path-style
  restriction); a managed-S3 future must keep the same public-origin pattern.

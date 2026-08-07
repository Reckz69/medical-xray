# ADR-013: HTTPS / Ingress Architecture — Caddy at the edge

- **Status:** Accepted
- **Date:** 2026-08-08
- **Deciders:** Architecture review (Sprint 4D)
- **Related:** [ADR-012](ADR-012-deployment-architecture.md), [ADR-014](ADR-014-secrets-management.md), `deploy/production/Caddyfile`

## Context

Production exposes exactly two HTTP endpoints: the gateway API
(`/api/v1/*`, plus `/health/*`, `/metrics`, and Swagger under `API_PREFIX`) and
the Next.js frontend. Both must be served over HTTPS with a valid public
certificate. Internally, all services already speak plain HTTP on the compose
network, and there is no reason to encrypt inside the host — the private
network is a trust boundary.

The choice is *where TLS terminates* and *what manages certificates*.

## Decision

### TLS terminates at Caddy (reverse proxy at the edge)

Caddy is the single ingress on the VM:

- It listens on `:443` and `:80` and reverse-proxies:
  - `api.<domain>` → `gateway:8000`
  - `<domain>` (and `www.<domain>`) → the frontend container (or Vercel, per
    ADR-016)
- It terminates TLS; every upstream sees only plain HTTP on the internal
  network.

### Automatic certificates via Caddy's ACME integration

Caddy obtains and renews Let's Encrypt certificates automatically
(`certificates: ACME`, HTTP-01 or DNS-01 as configured). No Certbot cron, no
manual certificate files, no certificate rotation runbook. The production
compose file passes `ACME_EMAIL` and the site address via env; Caddy persists
its data directory to a volume so renewals survive container restarts.

### Internal services stay plain HTTP, unexposed

Postgres, Redis, RabbitMQ, and MinIO publish **no host ports** in the
production file (unlike the dev file, which publishes them for local tooling).
They are reachable only by service name on the compose network. MinIO's S3 API
is consumed over the internal network by gateway/worker/scheduler; if the
object store ever needs public access, that is a documented, separate decision.

### Kubernetes alternative: ingress-nginx + cert-manager

If the system migrates to Kubernetes (ADR-012), the same edge role is played by
an ingress controller:

- `Ingress` resources route `api.<domain>` → gateway Service and `<domain>` →
  frontend Service.
- `cert-manager` issues ACME certificates via an `Issuer`/`ClusterIssuer`
  (Let's Encrypt) and stores them in `Secret`s; the `Ingress` references
  `cert-manager.io/cluster-issuer` via annotation.
- Reference manifests in `deploy/k8s/` use this pattern.

The Caddy decision and the ingress-nginx decision are equivalent at the
application layer: both terminate TLS in front of the same plain-HTTP services.

## Alternatives considered

- **Nginx + Certbot** — rejected. Two components to install, configure, and
  keep in sync (web server config + a cert renewal cron). Caddy folds both into
  one binary and one config file with automatic renewal.
- **TLS inside every service** — rejected. Requires certificates, key material,
  and SNI handling in every container for zero benefit inside a private
  network.
- **Cloud load balancer / ALB (TLS offload)** — a valid option once a managed
  cloud target is chosen (deferred with infrastructure automation, ADR-012);
  Caddy remains the default for the compose-VM path.

## Consequences

**Positive**
- Automatic, self-renewing HTTPS with zero certificate operations.
- One small config file (`Caddyfile`) is the entire edge.
- Internal services are not exposed to the public internet.

**Negative**
- Caddy is one more running container; its data volume must be backed up with
  the rest (renewal state, though re-issuable).
- HTTP-01 certificate issuance requires the domain's A record to point at the
  VM before the first boot.
- A managed cloud (ALB/ACM) would replace Caddy later only if the target cloud
  demands it; the app layer is unaffected.

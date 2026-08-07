# ADR-012: Production Deployment Architecture — Docker Compose on a VM

- **Status:** Accepted
- **Date:** 2026-08-08
- **Deciders:** Architecture review (Sprint 4D)
- **Related:** [ADR-011](ADR-011-model-artifacts.md), [ADR-013](ADR-013-https-ingress.md), [ADR-014](ADR-014-secrets-management.md), [ADR-015](ADR-015-persistent-state.md), [ADR-016](ADR-016-image-registry.md), [ADR-017](ADR-017-versioning-release.md)

## Context

The system has a validated, all-container development stack
(`backend/deploy/docker-compose.yml`): three app services (gateway, worker,
scheduler) plus PostgreSQL, Redis, RabbitMQ, MinIO, and a removable
observability overlay (OTel Collector, Prometheus, Grafana). CI/CD and image
distribution are in place (Sprint 4C + this sprint's ADR-016). What does not
exist yet is a definition of *where production runs* and *how someone deploys
it*.

The deployment must match the project's scale: a handful of services, a small
team, low traffic. It must also leave an honest path to scale out when that
scale assumption changes.

## Decision

### Canonical deployment: Docker Compose on a single Linux VM

The canonical production topology is the existing compose stack running on one
VM (any of AWS EC2, DigitalOcean, Hetzner, GCP — the choice is deferred to
infrastructure automation, see ADR-016 and the Terraform reference in
`deploy/terraform/`). Rationale:

- **It matches what is tested.** Every service image is the one CI builds and
  the stack is exercised end-to-end by `verify_all.sh` and `ci-full.yml`. The
  deployment path adds no new runtime semantics.
- **Operationally honest at this scale.** A single VM with one gateway, one
  worker, and one scheduler is more than sufficient for the current load, and
  far cheaper and simpler to operate than a cluster.
- **Docker Compose is the supported orchestrator** for single-host, process
  hygiene, restart policies, healthchecks, and networking are all already in
  the compose files.

The production compose file lives at `deploy/production/docker-compose.yml`
(see ADR-013 for the edge, ADR-014 for secrets, ADR-015 for state).

Two supported deployment modes (documented in `docs/engineering/deployment.md`):

- **Dev / first deployment:** `docker compose build && docker compose up -d` —
  builds from source on the host, no registry required.
- **CI-produced artifacts:** `docker compose pull && docker compose up -d` —
  pulls the GHCR images published by CI (ADR-016). Switching modes is a
  `build:` → `image:` change; the file keeps both seams.

### HTTPS with Caddy

TLS terminates at Caddy (ADR-013), which reverse-proxies the gateway and the
frontend. Infra services (Postgres, Redis, RabbitMQ, MinIO) are never exposed
beyond the host.

### Persistent volumes

Postgres, Redis, RabbitMQ, and MinIO persist to Docker volumes on the VM's disk
(ADR-015), with the object store optionally targeting S3 via the existing
`STORAGE_PROVIDER` seam. Backups are defined in ADR-015 and the Phase 5
runbooks.

### Secrets

Credentials are generated, injected via environment/secrets at runtime, and
rotated (ADR-014). No default or development credentials ship in the
production file.

### Monitoring

The observability overlay (OTel, Prometheus, Grafana) is part of the
production topology, retained as a removable overlay so the core stack never
depends on it (per `docs/AI_ENGINEERING_GUIDE.md`).

### Scaling limitations

A single VM caps throughput and availability:

- **Compute:** one CPU/RAM budget shared by all services; the worker (TF model
  inference) dominates.
- **Availability:** a VM restart or maintenance window takes the whole stack
  down; there is no multi-node redundancy.
- **Vertical headroom only:** scaling up is buying a bigger VM, which has
  ceilings and cost cliffs.

Within these limits, one dimension is already horizontal: RabbitMQ competing
consumers mean **additional worker replicas can be added on the same VM** (or a
second worker host pointed at the same queue) to raise inference throughput
without changing queue semantics.

### Migration to Kubernetes

The Kubernetes path is a documented alternative, not the default. The migration
is warranted when two or more of these hold: sustained load exceeds one VM's
headroom, the team needs self-healing/multi-zone availability, or HPA-based
scaling becomes the operating model. The reference manifests in `deploy/k8s/`
and the scaling notes in `docs/engineering/scaling.md` describe that path; the
compose services map one-to-one onto Deployments, so nothing about the app
logic needs to change to migrate.

### Infrastructure automation plan

Infrastructure as Code is intentionally **not** production-ready yet. The
Terraform scaffold in `deploy/terraform/` is a reference outline ("Reference
scaffold. Not production-ready."), to be replaced in a later sprint (4E) once a
cloud target is chosen and the manual VM deployment has been proven. This
avoids automating an architecture that may still change.

## Alternatives considered

- **Kubernetes as the default** — rejected. Overkill for one-to-few services:
  cluster control plane, ingress, and node management cost far more than the
  single VM they would be replacing, with no current availability requirement.
- **Fully managed services (RDS/ElastiCache/etc.) as the default** — rejected
  for now. Trades monthly cost and vendor lock-in for operational simplicity
  the project does not yet need. Documented as an alternative in ADR-015.
- **PaaS (Vercel/Heroku/Fly) for the backend** — rejected. The app is
  stateful, long-running, and queue-driven; a container VM maps directly onto
  the tested compose model. (The Next.js frontend may still deploy to Vercel —
  see ADR-016.)

## Consequences

**Positive**
- Production runs the exact stack that CI tests; no new runtime semantics.
- Cheapest operational model available for the current scale.
- A clearly documented, incremental path to Kubernetes and to managed
  infrastructure when the scale assumption breaks.
- Compose stays the single source of truth for service topology.

**Negative**
- Single point of failure at the VM level; availability is one-host.
- Manual VM provisioning (SSH, Docker install, compose pull/up) until
  infrastructure automation (Sprint 4E) lands.
- Scale-out requires either buying a bigger VM or beginning the Kubernetes
  migration.

# ADR-014: Secrets Management

- **Status:** Accepted
- **Date:** 2026-08-08
- **Deciders:** Architecture review (Sprint 4D)
- **Related:** [ADR-012](ADR-012-deployment-architecture.md), `deploy/production/docker-compose.yml`, `deploy/production/.env.example`, `deploy/production/generate-secrets.sh`

## Context

The stack has real secrets: PostgreSQL password, Redis (none by default, but
configurable), RabbitMQ user/password, MinIO root credentials, JWT signing
secret, Grafana admin password, and (for GHCR pulls on non-CI hosts) a
registry token. The development files ship insecure defaults (`change-me-in-prod`
JWT, `minioadmin`, `denoise/denoise`) by design — production must not.

The deployment is a single VM running compose; there is no managed secret
store. The decision is how secrets are generated, stored at rest, injected,
and rotated without inventing machinery the platform does not provide.

## Decision

### Secrets are generated, not committed

- `deploy/production/generate-secrets.sh` creates a `.env` file on the host
  using `openssl rand` for every credential (JWT, Postgres, RabbitMQ, MinIO,
  Grafana) and prints the generated values once.
- `.env` is gitignored and never committed; the committed `.env.example`
  contains only placeholders and instructions.
- The VM operator runs the generator once at first deployment.

### Injection via environment, with compose `secrets` where a file is preferred

- App services (gateway, worker, scheduler) read secrets from environment
  variables, sourced from `.env` (Compose `env_file`). This matches the
  existing configuration code (`pydantic-settings` reads env vars); no app
  change is required.
- Infra services (Postgres, RabbitMQ, MinIO) receive their credentials via
  compose `environment`/`env_file` in the same way.
- Where a file-based secret is cleaner (e.g. a registry credential for
  `docker login`, or a future client certificate), Compose `secrets` mounts the
  file read-only into the container. The production file uses `secrets` for
  anything the code or tooling reads as a path.

### Scope and rotation

- **JWT_SECRET:** rotated by generating a new value and restarting the gateway;
  refresh tokens carry `jti` and the rotation runbook in Phase 5 covers
  re-issuance.
- **Postgres/RabbitMQ/MinIO:** rotated by changing the value in `.env`,
  running the rotation SQL/`mc admin user` step, and restarting services that
  hold pooled connections. Documented in `docs/engineering/secret-rotation.md`.
- **Registry token (GHCR pull):** rotated via GitHub PAT; used only by
  `docker login ghcr.io` on the VM, never committed.

### Kubernetes alternative: platform-managed secrets

If the system migrates to Kubernetes (ADR-012), plaintext `Secret` manifests
are avoided in favor of:

- **SealedSecrets** (Bitnami) — `SealedSecret` CRs commit an encrypted blob;
  the controller decrypts into a `Secret` in-cluster. Operator-friendly, no
  extra cloud dependency.
- Or a **cloud secret manager** (AWS Secrets Manager / GCP Secret Manager)
  referenced by name, with a controller syncing values into `Secret`s.

The reference manifests in `deploy/k8s/` ship `Secret` placeholders annotated
to be filled by the chosen mechanism, not plaintext values.

## Alternatives considered

- **Vault (HashiCorp)** — rejected for now. Full-featured but heavy for a
  single VM; a managed store or SealedSecrets covers the need with far less
  machinery. Revisit if the project grows a team and central policy.
- **Committed encrypted secrets (SOPS)** — rejected for now. Adds a
  pre-commit encryption workflow and key management for a single-host
  deployment; the `.env` + file-permissions model is simpler and equally safe
  at this scale.
- **Hard-coded defaults in the production file** — rejected. The entire point
  of the production file is that no default credential works.

## Consequences

**Positive**
- No secret is committed; every credential is unique per deployment and
  generated locally.
- Zero new runtime components on the VM (no Vault server to operate).
- The same env-var model the app already uses, so no code change.

**Negative**
- `.env` on the VM is the single trust anchor: it must be file-permission
  locked (`chmod 600`) and backed up (or re-generatable) — documented in the
  runbooks.
- Rotation is a manual, documented procedure rather than a platform feature.
- Migrating to Kubernetes later requires moving values from `.env` into the
  chosen `Secret` mechanism.

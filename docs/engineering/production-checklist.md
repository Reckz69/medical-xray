# Production Readiness Checklist

> Sprint 4D. Work through this before directing real traffic at the production
> deployment (`deploy/production/`, ADR-012). Every unchecked box is an
> explicit, accepted risk — record the decision, don't leave it silent. Threat
> model references (`SR-n`) point at `docs/security/threat-model.md`.

## 1. Edge & TLS (ADR-013)

- [ ] DNS: `api.<SITE_DOMAIN>` A record → VM public IP (before first Caddy boot).
- [ ] `ACME_EMAIL` set; a valid cert is issued (no HTTP-only access remaining).
- [ ] Only `:80`/`:443` open on the host firewall; every other port closed.
- [ ] `CORS_ORIGINS` in `.env` lists the real frontend origin(s).
- [ ] `wget -q --spider https://api.<SITE_DOMAIN>/health/ready` → 200.

## 2. Secrets & identity (ADR-014, SR-1)

- [ ] `./generate-secrets.sh` ran; no `__generate__` value remains in `.env`.
- [ ] `.env` is `chmod 600` and backed up (or re-generatable) in a password manager.
- [ ] No committed default credentials anywhere (`change-me`, `minioadmin`,
      `denoise/denoise`); `grep -R "minioadmin\|change-me" deploy/ backend/` is clean except dev files.
- [ ] `JWT_SECRET` ≥ 32 random bytes; JWT alg is HS256; refresh rotation works
      (SR-1: bcrypt constant-time, httpOnly cookies, register flag honored).
- [ ] GHCR pull works on the VM (`docker login ghcr.io`; `docker compose pull`).

## 3. Hardening (SR-3 / SR-5 — CURRENT GAP, must be scheduled)

- [ ] App images run **non-root** (currently `root`; needs Dockerfile `USER`
      + a writable TF cache dir — flagged in `deploy/production/docker-compose.yml`).
- [ ] Read-only root filesystem where possible (after non-root lands).
- [ ] Infra + app image tags **pinned** (`MINIO_IMAGE` is still `latest`).
- [ ] SAST/SCA in CI (bandit, pip-audit, gitleaks, trivy) — SR-5, scheduled.

## 4. Resource & runtime (ADR-012)

- [ ] Resource limits present (set in `deploy/production/docker-compose.yml`);
      verify with the VM's actual load and adjust.
- [ ] `restart: unless-stopped`; healthchecks green (`docker compose ps` all healthy).
- [ ] Model weights mounted `:ro` and `scripts/verify_weights.sh` passes on the VM.
- [ ] Single-VM ceiling understood and documented (ADR-012); `--scale worker=N`
      only when the VM has headroom.

## 5. Data & durability (ADR-015)

- [ ] Nightly backups scheduled (Postgres `pg_dump`, MinIO `mc mirror`,
      RabbitMQ definitions) **and copied off-site** (backup-restore.md).
- [ ] **Restore tested** at least once (quarterly); RPO ≤ 24 h / RTO ≤ 4 h met.
- [ ] Object lifecycle wired: `OBJECT_ARCHIVE_DAYS` / `OBJECT_DELETE_DAYS`
      match the MinIO ILM or S3 lifecycle rules (backup-restore.md).
- [ ] PostgreSQL WAL archiving decision recorded (follow-on for PITR).

## 6. Monitoring & alerting (ADR-010, 4B)

- [ ] Observability overlay up: `docker compose -f docker-compose.yml
      -f observability.yml up -d`.
- [ ] Prometheus scrapes gateway/worker/scheduler (`/metrics`); Grafana has at
      least one dashboard + an alert on: gateway down, worker queue growth,
      disk > 85%, backup failure.
- [ ] OTel traces visible (collector export target set — currently `debug`).

## 7. Operational practice

- [ ] Upgrade/rollback runbook read and practiced once (deployment.md,
      ADR-017 ordering rule: migrate schema before app, roll back app first).
- [ ] Secret rotation runbook read (secret-rotation.md); JWT rotation
      announced as a sign-out maintenance window.
- [ ] A person is on call; incident + runbook pointers are written down.

## 8. Threat-model coverage summary

| Requirement | Status |
| --- | --- |
| SR-1 (auth) | Implemented (verify bcrypt/cookies on a staging sign-in). |
| SR-2 (upload validation) | Implemented (magic bytes, size/dimension caps, checksum). |
| SR-3 (non-root, read-only, pinned deps) | **Gap — scheduled hardening.** |
| SR-4 (download audit, ownership, soft-delete) | Not yet a sprint (Sprint 5 security phase). |
| SR-5 (SAST/SCA in CI) | **Gap — scheduled (4E or security sprint).** |

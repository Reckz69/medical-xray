# Sprint 4D — Phase 1 Review: deployment ADRs (ADR-012–017)

- **Status:** Review-complete, ready to commit
- **Date:** 2026-08-08
- **Branch:** `main`
- **Related:** `docs/README.md` (ADR log), `docs/CHANGELOG.md`, the prior sprint review `docs/reviews/sprint-4c-review.md`

## Goal

Lock the production deployment architecture before any config or code is
written. Phase 1 delivers six ADRs that decide *where* production runs, *how it
is secured, exposed, and persisted*, and *how every artifact is versioned* — so
the later phases (compose, GHCR, k8s/terraform, operations) implement an agreed
architecture rather than inventing one.

## Delivered

- **ADR-012 — Production deployment architecture.** Canonical: Docker Compose
  on a single Linux VM (Caddy TLS, volumes, backups, secrets, monitoring),
  with documented scaling limits, a migration path to Kubernetes, and a Terraform
  outline deferred to infrastructure automation (not production-ready).
- **ADR-013 — HTTPS/Ingress.** Caddy terminates TLS (automatic ACME
  certificates); internal services stay plain HTTP and unexposed; Kubernetes
  alternative is ingress-nginx + cert-manager.
- **ADR-014 — Secrets management.** Credentials generated locally
  (`generate-secrets.sh`), injected via `.env`/compose `secrets`, rotated via
  documented runbooks; no committed or default credentials in production.
- **ADR-015 — Persistent state.** Postgres/Redis/RabbitMQ/MinIO self-hosted in
  containers with volumes; managed services (RDS/ElastiCache/MQ/S3) documented
  as the alternative; per-service backup strategy with RPO ≤ 24 h / RTO ≤ 4 h.
- **ADR-016 — Image registry.** Commits to GHCR and **reverses the ADR-011
  "no GHCR in v1" deferral**; CI publishes `gateway|worker|scheduler` with
  four tags (`latest`, `<sha>`, `<semver>`, `<sprint-tag>`); frontend stays
  Vercel/standalone.
- **ADR-017 — Versioning & release.** Semver product tags; sprint tags are
  history labels, not releases; image tag conventions; weights compatibility
  matrix; **Alembic schema revision** tracked as a first-class component of the
  version contract.
- **Index + supersede note.** `docs/README.md` ADR log extended with
  ADR-012–017; ADR-011 annotated that ADR-016 reverses its GHCR deferral.

## Decisions that shape the remaining phases

1. Compose-VM is canonical; Kubernetes is a documented alternative — the k8s
   manifests are reference material, not a supported deploy path.
2. Secrets are generated and injected, never committed — the production
   compose file must contain no working default credentials.
3. Images are published by CI to GHCR and consumed via `docker compose pull`;
   the compose file must support both `build` (dev/first deploy) and `pull`
   (CI artifacts) modes (ADR-012).
4. The version contract includes the Alembic revision — upgrade/rollback docs
   must pin schema + image + weights together.

## Validation

- All six ADRs reviewed against the current codebase state (compose services,
  env seams, `STORAGE_PROVIDER`, ADR-003/004, ADR-011) — decisions reference
  only existing seams, no new app requirements.
- ADR index rows match file names; links verified.

## Remaining

- Phase 2 (production compose + Caddy + secrets + two-mode deploy doc),
  Phase 3 (GHCR CI), Phase 4 (k8s + terraform reference), Phase 5 (operations,
  review docs, tag).

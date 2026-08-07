# Sprint 4D — Phase 4 Review: Kubernetes + Terraform reference architecture

- **Status:** Review-complete, ready to commit
- **Date:** 2026-08-08
- **Branch:** `main`
- **Related:** [ADR-012](../adr/ADR-012-deployment-architecture.md), [ADR-013](../adr/ADR-013-https-ingress.md), [ADR-014](../adr/ADR-014-secrets-management.md), [ADR-015](../adr/ADR-015-persistent-state.md), [ADR-016](../adr/ADR-016-image-registry.md), `docs/engineering/scaling.md`, `docs/reviews/sprint-4d-phase1-review.md`

## Goal

Document the scale-out alternatives to the canonical compose-VM deployment —
Kubernetes manifests and a Terraform outline — **as reference material only**,
explicitly not production-ready, so future contributors understand the path
without mistaking the scaffold for a supported deployment.

## Delivered

### Kubernetes reference manifests (`deploy/k8s/`)

| File | Contents |
| --- | --- |
| `README.md` | **"Reference scaffold. NOT a supported deployment path."** — when to migrate (ADR-012), compose→K8s mapping table, apply order, secrets/weights/images notes, validation caveat. |
| `namespace.yaml` | `denoise-x` Namespace. |
| `configmap.yaml` | Non-secret app config mirroring `deploy/production/.env.example`. |
| `secrets.yaml` | Placeholders only (base64 `CHANGE_ME_*`), annotated for SealedSecrets / cloud manager (ADR-014); GHCR pull-secret note. |
| `gateway.yaml` | Deployment + ClusterIP Service + HPA (CPU 70%, min 2 / max 6) + PDB; env wiring with `$(VAR)` expansion. |
| `worker.yaml` | Deployment + **commented KEDA ScaledObject** (RabbitMQ queue depth); weights-mount pattern documented via init container/PV comment. |
| `scheduler.yaml` | Deployment (replicas 1 — Redis-locked cleanup) + Service + PDB. |
| `ingress.yaml` | Ingress + cert-manager ClusterIssuer annotation (replaces Caddy, ADR-013); frontend ingress commented out (Vercel default). |
| `state.yaml` | PVCs + StatefulSets (postgres, rabbitmq) / Deployments (redis, minio) + headless/ClusterIP Services; StorageClass comment. |

### Scaling design (`docs/engineering/scaling.md`)

- Load profiles: gateway (QPS/CPU), worker (queue depth), scheduler (fixed 1).
- Single-VM guidance: workers already scale horizontally via RabbitMQ competing
  consumers (`--scale worker=2`); everything else vertical until K8s.
- K8s path: gateway HPA on CPU; **worker KEDA on queue depth** (why not CPU —
  it reacts to saturation, not backlog); scheduler fixed with PDB.

### Terraform scaffold (`deploy/terraform/`)

- `README.md` — **"Reference scaffold. NOT production-ready."**; why IaC is
  deferred (provider/topology undecided, ADR-012); the 4E sequence (choose
  cloud → replace scaffold with deployable config → remote state/locking).
- `aws/{providers.tf,variables.tf,main.tf}` — AWS-flavored starting point only:
  provider + local state, VPC/subnet/IGW/instance/bucket skeleton. Explicitly
  not deployable (no IAM, security groups, DNS/TLS, monitoring, outputs).

## Decisions

1. **K8s files are reference, not supported** — the README states it in the
   first lines and each manifest carries the same banner.
2. **Terraform is a labeled scaffold** — `aws/` is illustrative (most common
   choice), not a commitment to AWS; no remote state, no `terraform apply`
   implication. Validation is optional/local-only.
3. **Stateful services are StatefulSets** where ordering/identity matters
   (postgres, rabbitmq); redis/minio as Deployments + PVC — a defensible
   reference split, documented in the mapping table.
4. **Weights in K8s** follow ADR-011: an init container fetching the release
   into an emptyDir (or a PV with the verified file) — the worker mounts
   `:ro`; `verify_weights.sh` still applies.

## Validation

- All 8 manifests parse via `yaml.safe_load_all` (backend venv) — OK.
- `kubectl apply --dry-run=client` requires a cluster server (openapi/API-group
  discovery), so it cannot run without one; this is documented in the README
  ("YAML-parse-checked in the repo gate only").
- Terraform not installed locally → `fmt`/`validate` skipped (optional per
  plan); scaffold is intentionally incomplete.
- GHCR image refs in manifests match ADR-016 (`ghcr.io/Reckz69/<service>`,
  pin-tag comments per ADR-017).

## Remaining

- Phase 5 (operations: backups/restore, rotation, production checklist,
  diagrams), review docs, CHANGELOG/ADR-index/docs sync, tag `sprint-4d`, push.
- Sprint 4E (future, IaC-only): choose cloud, replace the Terraform scaffold
  with a deployable configuration, remote state + locking.

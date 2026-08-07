# ADR-017: Versioning & Release Strategy

- **Status:** Accepted
- **Date:** 2026-08-08
- **Deciders:** Architecture review (Sprint 4D)
- **Related:** [ADR-016](ADR-016-image-registry.md), [ADR-011](ADR-011-model-artifacts.md), [ADR-012](ADR-012-deployment-architecture.md), `docs/CHANGELOG.md`

## Context

Production now has **five independently versionable things**: the source tree,
sprint tags, published container images (ADR-016), GitHub Releases (weights
and, potentially, source releases), and the database schema (Alembic
migrations). Without a stated convention these drift apart: a deploy pinned to
image `v1.0.0` might be paired with weights that were trained for a different
model contract, or with a DB schema the code does not expect.

The goal is a single, auditable version story: any deployed system can be
described by one row, and every upgrade is a small, verifiable step.

## Decision

### Semantic versioning for the product

The product version is **semver** (`MAJOR.MINOR.PATCH`):

- **MAJOR:** breaking change — incompatible schema migration, breaking API,
  incompatible model contract.
- **MINOR:** backward-compatible feature (new endpoint, new capability).
- **PATCH:** backward-compatible fix.

The canonical tag is `v<MAJOR>.<MINOR>.<PATCH>`, e.g. `v1.0.0`. The app's
`MODEL_VERSION` (default `v1.0.0`) is the model contract version, released in
lockstep with the product where the contract demands it.

### Sprint tags describe *what was built*, not *what runs*

Sprint tags (`sprint-4d`) are **history labels**: they identify the exact
source + image set a sprint produced. They are not release versions — a sprint
may produce zero releases. `sprint-4d` images are
`ghcr.io/.../worker:sprint-4d`; a release image is `.../worker:v1.0.0`.

### Container image tags (ADR-016)

| Tag | Meaning |
| --- | --- |
| `latest` | current default |
| `<git-sha>` | exact commit, immutable |
| `v<semver>` | release artifact, immutable |
| `<sprint-tag>` | sprint boundary, immutable |

### Release process

1. Gates green on `main` (fast + full CI).
2. Commit bumps: CHANGELOG entry, `MODEL_VERSION` if the model contract
   changed, Alembic migration if schema changed.
3. Tag `v<semver>` (and push); CI publishes images tagged
   `v<semver>` (+ `latest` + `<sha>`) and, when applicable, a GitHub Release
   for artifacts (weights, per ADR-011).
4. Deployment pins a concrete tag (`v<semver>` or `<sha>`) — never a
   moving `latest` for a known-good upgrade.

### Model weights compatibility

Model weights are versioned independently (`weights-vN` releases, ADR-011) but
their **compatibility** with product versions is explicit. A weight bump that
changes the model contract (input shape, tile size, output semantics) is a
**MINOR** product bump; a behavior-breaking change is **MAJOR**.

### Database schema compatibility

The Alembic migration history is part of the version contract. A deploy pins
both the app image **and** the schema revision it expects; upgrade ordering is
"run migrations forward, then start new app" (see
`docs/engineering/deployment.md` for the upgrade/rollback runbook).

## Compatibility matrix

The deployed system must always be describable by one row. Example for the
first release:

| Component | Version |
| --- | --- |
| Git tag | `v1.0.0` |
| Sprint tag | `sprint-4d` |
| Gateway image | `ghcr.io/.../gateway:v1.0.0` |
| Worker image | `ghcr.io/.../worker:v1.0.0` |
| Scheduler image | `ghcr.io/.../scheduler:v1.0.0` |
| Model weights | `weights-v1` |
| Database schema | Alembic revision `<rev>` |

Compatibility rules:

| Product version | Weights | Note |
| --- | --- | --- |
| `v1.0.x` | `weights-v1` | `MODEL_VERSION=v1.0.0` contract |
| `v1.1.x` | `weights-v2` | new model contract (MINOR) |
| `v2.x.x` | per contract | breaking change (MAJOR) |

The matrix is recorded per release in the CHANGELOG so the pairing is
auditable after the fact.

## Alternatives considered

- **No formal versioning (tags as needed)** — rejected. Five independently
  versionable things without a contract is exactly the drift this ADR exists
  to prevent.
- **`latest`-only image tags** — rejected (ADR-016): not reproducible, and
  upgrades become "whatever is current."
- **Coupling weights to the product version (`v1.0.0` == `weights-v1`)** —
  rejected. Weights version independently and may change within a patch series
  (e.g. retrained weights, same contract); the compatibility table records the
  pairing instead of forcing an identity.

## Consequences

**Positive**
- Every deployment is one auditable row (image + weights + schema revision).
- Upgrades and rollbacks are explicit steps with a known pairing.
- Sprint tags stay honest history labels; semver carries release meaning.

**Negative**
- Release bookkeeping: every release updates the matrix + CHANGELOG
  (documented, but manual).
- Moving `latest` must be disciplined — the upgrade runbook pins concrete tags.
- Schema drift silently breaks deploys if the migration ordering is ignored;
  the runbook makes the ordering mandatory.

# ADR-016: Image Registry — GitHub Container Registry (GHCR)

- **Status:** Accepted
- **Date:** 2026-08-08
- **Deciders:** Architecture review (Sprint 4D)
- **Related:** [ADR-012](ADR-012-deployment-architecture.md), [ADR-011](ADR-011-model-artifacts.md), [ADR-017](ADR-017-versioning-release.md), `.github/workflows/ci-images.yml`

## Context

Sprint 4C deferred an image registry ("no GHCR in v1", recorded in ADR-011):
CI built and tested images but never published them, so production deployment
meant building from source on the host. Sprint 4D defines production
deployment (ADR-012). For the "CI-produced artifacts" deployment mode
(`docker compose pull`) to work, published images must exist somewhere.

GitHub is already the single trust anchor: source, CI, releases, and (via
ADR-011) model weights. Choosing GitHub Container Registry keeps the artifact
story in one place, and the built-in `GITHUB_TOKEN` can push images with
`packages: write` — no external credentials.

## Decision

### Images are built and published to GHCR by CI

A dedicated workflow (`ci-images.yml`) builds the three backend images and
pushes them to GHCR:

- `ghcr.io/reckz69/gateway`
- `ghcr.io/reckz69/worker`
- `ghcr.io/reckz69/scheduler`

`reckz69` is a **user** namespace: GitHub only allows the
`OWNER/REPO/IMAGE` nesting for organizations, so the images are
`ghcr.io/USER/<image>`, not nested under the repository name. The workflow
derives the owner from `github.repository_owner`, so the path stays correct if
the repository ever moves under an org. The owner is **lowercased** in the
reference: Docker requires lowercase repository names (GHCR itself is
case-insensitive, so `ghcr.io/reckz69/*` resolves the same image as the
`Reckz69` owner). Sprint 4E corrected the reference to the lowercase form.

The three images map directly to the existing Dockerfiles
(`backend/{gateway,worker,scheduler}/Dockerfile`). The frontend is **not**
published to GHCR — it deploys to Vercel (or as a Next.js standalone build), a
separate frontend concern (see below).

### Trigger and permissions

- Triggered on pushes to `main` and on sprint tags (`sprint-*`), so the same
  workflow that publishes a sprint's source also publishes its images.
- Uses `GITHUB_TOKEN` with `packages: write` and `contents: read`
  (`permissions` block) — works on private repos with no PAT, no `read:org`
  requirement (the local `gh` limitation does not apply to Actions).
- Publishes only **after the gates pass**: images are tagged from the
  validated source the fast/full gates already proved (the tag workflow runs
  against `main`/sprint-tag pushes, which are gated states by definition).

### Tagging (four tags, per ADR-017)

Each build is pushed with four tags:

| Tag | Value | Purpose |
| --- | --- | --- |
| `latest` | `latest` | current default |
| `<git-sha>` | full commit SHA | exact code, reproducible |
| `<semver>` | e.g. `v1.0.0` | release artifact (ADR-017) |
| `<sprint-tag>` | e.g. `sprint-4d` | exactly what the sprint produced |

### Consumption

The production compose file's "CI-produced artifacts" mode (`docker compose
pull`) references these images; the "dev / first deployment" mode builds from
source (`docker compose build`) with no registry needed (ADR-012). The
Kubernetes reference manifests (`deploy/k8s/`) reference the same images.

### This supersedes the ADR-011 deferral

ADR-011 recorded "no GHCR in v1". This ADR **reverses that clause**: GHCR is
now the registry for backend images. ADR-011's weights-via-Releases decision is
unchanged — weights stay a Release asset (they are downloaded into the build
context or mounted at runtime, not baked into an image).

## Alternatives considered

- **Docker Hub** — rejected. Public by default, rate-limited pulls, and a
  separate account/login from the GitHub identity the project already uses.
- **Private registry (Harbor/self-hosted)** — rejected. An extra component to
  operate on the VM for zero benefit over GHCR at this scale.
- **No registry (build on host)** — retained as the dev/first-deployment mode
  (ADR-012), but rejected as the only mode: `docker compose pull` needs a
  published image source for reproducible upgrades.
- **Frontend container image** — deferred. The Next.js app has no Dockerfile
  today; its deployment target (Vercel vs standalone container) is a frontend
  decision, documented in `docs/engineering/deployment.md`.

## Consequences

**Positive**
- CI produces versioned, reproducible images; deployment is `docker compose
  pull && up` with pinned tags.
- No new identity: `GITHUB_TOKEN` pushes to GHCR; operators `docker login
  ghcr.io` with a PAT (or a deploy token).
- Completes the pipeline: source → CI gates → images → deploy.

**Negative**
- GHCR package storage for three images × history grows with each push
  (cleanup policy to be defined — images are immutable by tag convention).
- First pull from a fresh VM requires `docker login ghcr.io` with a
  credentials file (ADR-014).
- The frontend remains outside this pipeline until its own deployment is
  decided.

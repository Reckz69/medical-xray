# Sprint 4D — Phase 3 Review: GHCR image publishing

- **Status:** Review-complete, ready to commit
- **Date:** 2026-08-08
- **Branch:** `main`
- **Related:** [ADR-016](../adr/ADR-016-image-registry.md), [ADR-017](../adr/ADR-017-versioning-release.md), `docs/reviews/sprint-4d-phase1-review.md`, `docs/reviews/sprint-4d-phase2-review.md`

## Goal

Make the "CI-produced artifacts" deployment mode real (ADR-012): CI builds the
three backend images and publishes them to GHCR so a production host runs
`docker compose pull` instead of building from source. This is the sprint's
only executable change.

## Delivered

- **`.github/workflows/ci-images.yml`** — builds + pushes `gateway`, `worker`,
  `scheduler` to `ghcr.io/<owner>/<service>`:
  - Triggers: pushes to `main`, tags `v*` and `sprint-*`, plus
    `workflow_dispatch`.
  - **Four tags per image** (ADR-017): `latest` (main + `v*`), full `<sha>`
    (every push), `v<semver>` (`v*` tags), `<sprint-tag>` (`sprint-*` tags).
  - `permissions: packages: write` — `GITHUB_TOKEN` publishes to GHCR with no
    PAT and no `read:org` (the local `gh` limitation does not apply to
    Actions).
  - Matrix over the three services; `fail-fast: false`; Buildx GHA layer cache
    scoped per service.

## Decisions

1. **Explicit tag computation, not `docker/metadata-action`.** `latest` must
   update on both default-branch pushes and `v*` tags, which the metadata
   action's `enable` expressions cannot express cleanly. A 12-line `case`
   statement produces exactly ADR-017's four tags and is trivially auditable.
2. **Weights are not baked into images** (ADR-011/016): the worker mounts them
   `:ro` at runtime, so this workflow needs no weights step and the images stay
   lean and rebuildable.
3. **Only backend images.** The frontend has no Dockerfile; it deploys to
   Vercel/Next-standalone (ADR-016) and is out of this workflow's scope.
4. **`github.repository_owner`, not a hard-coded path.** For the user account
   GHCR only allows `ghcr.io/USER/<image>` (no `OWNER/REPO` nesting); deriving
   the owner keeps the path correct if the repo moves under an org.

## Validation

- `actionlint .github/workflows/ci-images.yml` → **clean**.
- Build contexts/dockerfiles match the existing `backend/{gateway,worker,
  scheduler}/Dockerfile` paths (context `backend`, file
  `backend/<service>/Dockerfile`).
- Tag matrix walked by hand for the three trigger cases (main → `latest`+`sha`;
  `v*` → `v`+`latest`+`sha`; `sprint-*` → `sprint`+`sha`).

## Remaining

- Phase 4 (k8s/terraform reference) will reference these images; Phase 5
  (operations, docs/changelog, review docs, tag).
- First real push happens on the next `main` push or sprint tag after this
  lands — GHCR packages are auto-created on first push.

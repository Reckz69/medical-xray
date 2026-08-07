# Continuous Integration

Denoise X uses GitHub Actions. Three workflows plus a manual-only benchmark,
designed so every push gets fast feedback and every merge gets full validation
without paying the full cost on every commit.

## Workflow overview

```
ci.yml (fast)                    ci-full.yml (full)
─────────────────────            ───────────────────────────────
push → sprint/**                 PR → main
                                 push → main
                                 workflow_dispatch (manual)
                                 │
  backend  frontend              validate (compose config -q)
  ───────  ───────               │
  ruff     tsc                   ├─ backend  (ruff → mypy → pytest → golden)
  mypy     eslint                ├─ frontend (tsc → eslint)
  pytest                          └─ build   (docker compose build gateway worker scheduler)
                                     └─ e2e   (full stack up → Playwright, LAST)
                                             (uploads playwright-report on any outcome)

ci-images.yml (publish)          workflow_dispatch additionally runs:
─────────────────────            benchmark (CPU baseline; uploads its report)
push → main
tag → v* / sprint-*              ──
workflow_dispatch                │
                                 │
  build + push → GHCR (gateway, worker, scheduler)
  tags: latest, <sha>, v<semver>, <sprint-tag>   (ADR-016/017)
```

`ci-full.yml` stages are deliberately ordered so expensive work never runs on a
broken foundation: `validate` fails fast on bad compose files before any test,
build, or E2E spend.

## Trigger table

| Trigger | Workflow | Runs |
| --- | --- | --- |
| push to `sprint/**` | `ci.yml` (fast) | ruff, mypy, unit+integration pytest, tsc, eslint |
| pull request → `main` | `ci-full.yml` | full chain incl. golden, Docker build, Playwright E2E |
| push to `main` | `ci-full.yml` + `ci-images.yml` | full chain + publish images to GHCR |
| tag `v*` / `sprint-*` | `ci-images.yml` | publish images to GHCR |
| manual `workflow_dispatch` | `ci-full.yml` + `benchmark` (+ `ci-images.yml`) | full chain + CPU benchmark (+ publish) |

Both CI gates use `concurrency: cancel-in-progress`, so a newer push cancels
the superseded run for the same ref. `ci-images.yml` also uses it.

The unit + integration pytest suite drives the real worker, which loads the
model from the repo root — so **both** workflows download and verify the
weights from the `weights-v1` release (via `GITHUB_TOKEN` + the ADR-011
manifest) before pytest. What the fast gate skips is the expensive goldens,
Docker build, and Playwright E2E.

## Required GitHub secrets

**None.** The only credential used is the built-in `GITHUB_TOKEN` (see
[ADR-011](../adr/ADR-011-model-artifacts.md)); each job sets
`permissions` explicitly: `contents: read` on the gates, and
`contents: read` + `packages: write` on `ci-images.yml` (GHCR publishing,
ADR-016). The weights are downloaded from a GitHub Release on the same
repository with `GH_TOKEN: ${{ github.token }}`, which works on private repos
without storing a PAT or a service-account secret. A production host that runs
`docker compose pull` needs its own `docker login ghcr.io` credential
(ADR-014), which is a deploy-time secret, not a CI secret.

## Image publishing (ADR-016/017)

`ci-images.yml` builds `gateway`, `worker`, `scheduler` and pushes them to
`ghcr.io/<owner>/<service>`, tagged four ways:

| Tag | When |
| --- | --- |
| `<full-sha>` | every run (immutable) |
| `latest` | `main` pushes and `v*` tags |
| `v<semver>` | `v*` tags (release artifact) |
| `<sprint-tag>` | `sprint-*` tags (sprint boundary) |

Production consumes them in the "CI-produced artifacts" mode
(`docker compose pull`, `deploy/production/`); the "dev / first deployment"
mode builds from source and needs no registry. The owner is
`github.repository_owner`, **lowercased** (`${{ lower(github.repository_owner) }}`)
— Docker image references are lowercase-only, so the workflow lowercases the
owner and `.env`/compose use `ghcr.io/reckz69` (GHCR normalizes case, so
`ghcr.io/Reckz69/...` and `ghcr.io/reckz69/...` are the same artifact) — see
ADR-016.

## Weights release process (ADR-011)

The model artifact `n2n_unet_best_weights04.keras` (~89 MB) is gitignored
and served from GitHub Release `weights-v1`. To publish a new model:

1. Export/build the new `.keras` file.
2. Compute its checksum and size:
   ```sh
   shasum -a 256 "n2n_unet_best_weights04.keras"
   stat -f%z "n2n_unet_best_weights04.keras"
   ```
3. Update `scripts/weights.sha256` (name, size, sha256) — commit it.
4. Create the GitHub Release and upload the asset:
   ```sh
   gh release create weights-vN "n2n_unet_best_weights04.keras"
   ```
5. Bump `MODEL_VERSION` in `backend/.env.example` and
   `backend/gateway/core/config.py` to match the release (keep `weights-vN` ↔
   `MODEL_VERSION` in lockstep).
6. Commit + push. CI (and `scripts/verify_all.sh`) verifies filename, size,
   and SHA-256 before any weight-gated test runs; a missing or corrupt asset
   **fails** the job rather than silently skipping tests.

## Cache strategy

| Cache | Where | Mechanism |
| --- | --- | --- |
| Python deps | `backend` job, `actions/setup-python` | `cache: pip`, keyed by `backend/requirements*.txt` hash |
| npm deps | `frontend` job, `actions/setup-node` | `cache: npm`, keyed by `frontend/package-lock.json` |
| Docker layers | `ci-full` build/e2e jobs | built on the E2E runner (hosted runners don't share images) |
| Image build layers | `ci-images.yml` | Buildx `type=gha` cache, scoped per service (`images-<service>`) |
| Infra containers | none | pulled fresh per run from `docker compose` |

Published images (GHCR) are the durable artifact: production pulls them
instead of rebuilding (`docker compose pull`, ADR-016); `latest` is a moving
tag, so upgrades pin `<sha>` / `v<semver>` / `<sprint-tag>` (ADR-017).

## How to rerun failed jobs

- **Rerun a single failed job** (the norm): on the failing run in the GitHub
  Actions UI, select the job and **Re-run jobs / Re-run failed jobs**. Skipped
  successors (`e2e` etc.) rerun once their dependency passes.
- **Rerun a whole workflow**: Actions → workflow → **Re-run all jobs**.
- **A flaky Playwright failure**: failure artifacts (HTML report + `trace.zip`
  under `frontend/test-results/`) are uploaded automatically with
  `if: always()`; inspect them before rerunning. The smoke test prefers an
  existing account via `E2E_EMAIL`/`E2E_PASSWORD` to dodge the 3/day signup cap.
- **Manual full run incl. benchmark**: Actions → **CI (full)** →
  **Run workflow** → branch → Run.

## Local equivalent commands

`scripts/verify_all.sh` mirrors `ci-full.yml` stage-for-stage, so CI and local
development cannot drift:

```sh
scripts/verify_all.sh   # validate → weights → ruff → mypy → pytest → golden → tsc → eslint → e2e
```

Prerequisites: `backend/.venv` (runtime + dev deps), `frontend/node_modules`,
valid weights at the repo root (`scripts/verify_weights.sh`), and — for the
final E2E stage — the full stack up (see `frontend/e2e/README.md`).

Per-stage commands, as CI runs them:

| Stage | Command |
| --- | --- |
| Compose validate | `docker compose -f backend/deploy/docker-compose.yml config -q` (+ `observability.yml`, + `docker-compose.test.yml`) |
| Weights verify | `bash scripts/verify_weights.sh` |
| Ruff | `cd backend && ./.venv/bin/python -m ruff check .` |
| Mypy | `cd backend && ./.venv/bin/python -m mypy --config-file mypy.ini` |
| Backend tests | `cd backend && ./.venv/bin/python -m pytest -q -p no:cacheprovider` |
| Golden | `cd backend && ./.venv/bin/python -m pytest -q -m golden -p no:cacheprovider` |
| TypeScript | `cd frontend && npx tsc --noEmit --incremental false` |
| ESLint | `cd frontend && npm run lint` |
| E2E | `cd frontend && npm run e2e` |
| Benchmark | `cd backend && ./.venv/bin/python scripts/benchmark_cpu.py --out ../docs/benchmarks/cpu-ci.md` |

Notes for running backend tests locally: infra must be up
(`docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.test.yml up -d`),
`backend/.env` must exist (`cp .env.example .env`), migrations applied
(`python -m alembic upgrade head`), and no worker/scheduler/gateway process
may be running on the host (they would compete with the tests).

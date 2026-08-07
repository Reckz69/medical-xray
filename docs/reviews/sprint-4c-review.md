# Sprint 4C — Review: CI/CD gates, weights distribution, deployment boot fixes

- **Status:** Review-complete; sprint merged to `main` (`9a10c46`) and tagged `sprint-4c`
- **Date:** 2026-08-08
- **Branch:** `sprint/3-real-ml` → merged into `main` as PR #3
- **Related:** [ADR-011](../adr/ADR-011-model-artifacts.md), `docs/engineering/ci.md`, `docs/AI_ENGINEERING_GUIDE.md`, `docs/reviews/sprint-4b-phase4-review.md`

## Goal

Turn a repo that "passed locally" into one whose CI proves it: a validate-first
local gate, fast and full GitHub Actions pipelines, a SHA-256-pinned model
weights distribution seam (ADR-011), and a scheduler test flake fixed at its
root. In practice the sprint also had to fix two deployment boot bugs and make
the fast gate drive the real model, because the "passes locally" state relied on
artifacts that existed only on the developer machine.

## Files Changed

| File | Change |
| --- | --- |
| `.github/workflows/ci.yml` | Fast gate (sprint push + PR). Added **Download model weights (weights-v1)** and **Verify weights integrity (ADR-011)** steps before pytest — the unit+integration suite drives the real worker/model, so a gate without weights was testing nothing. |
| `.github/workflows/ci-full.yml` | Full gate (PR → `main`): build, pytest, golden tests, tsc/eslint, weights download+verify, actionlint. |
| `scripts/verify_all.sh` | 9-stage local gate (compose validate, weights, ruff, mypy, pytest, golden, tsc/eslint, full-stack build + e2e smoke, final summary). |
| `scripts/weights.sha256`, `scripts/verify_weights.sh` | Committed manifest (name/size/sha256) + loud-failure verify script. |
| `docs/adr/ADR-011-model-artifacts.md` | Model weights distributed via GitHub Releases, verified by committed manifest; GHCR deferred. |
| `backend/requirements.txt` | + `email-validator` — pydantic `EmailStr` crash on gateway boot. |
| `backend/deploy/docker-compose.yml` | Weights bind mount `../` → `../../` (Compose resolves relative to `deploy/`); worker was crash-looping on a nonexistent `/weights` file. |
| `backend/ruff.toml`, `backend/requirements-dev.txt` | Ruff gate config + pinned dev tooling. |
| `backend/tests/test_scheduler.py` | Autouse `DELETE FROM jobs` fixture — retry tests counted *every* due `RETRYING` row in the persistent table, making the suite order/history-dependent. |
| `frontend/.gitignore` | `!src/lib/`, `!src/lib/*`, `!e2e/lib/`, `!e2e/lib/*` — the repo-root `.gitignore` bare `lib/` pattern had swallowed the frontend lib dirs. |
| `frontend/src/lib/{api.ts,auth.tsx,utils.ts}`, `frontend/e2e/lib/png.ts` | Now tracked (they never were). |
| 16 files (configs, tests, scripts, docs) | Canonicalize weights artifact to `n2n_unet_best_weights04.keras` (see Decisions). |
| `docs/engineering/ci.md`, `docs/CHANGELOG.md`, `docs/technical-debt.md`, `docs/README.md` | Sprint docs, changelog, debt register, ADR index. |

## Architecture Decisions

1. **Model weights ship via GitHub Releases, verified by a committed
   manifest** (ADR-011). Weights are too large to commit and too important to
   trust blindly: `scripts/weights.sha256` pins name/size/sha256, both workflows
   download `weights-v1` with `GH_TOKEN: ${{ github.token }}` and fail loudly on
   mismatch. No GHCR in v1 (reversed in Sprint 4D).

2. **The fast gate downloads weights too.** The pytest suite drives the real
   worker and model through `model_manager.py`, so a fast gate without weights
   produces false greens — the root cause of five CI failures that never
   reproduced locally.

3. **Canonical artifact name `n2n_unet_best_weights04.keras`.** GitHub
   sanitizes release asset names (space→`.`, strips parens), so the uploaded
   `n2n_unet_best_weights04 (2).keras` arrived as an un-renamable
   `n2n_unet_best_weights04.2.keras`. Canonicalizing removed the footgun behind
   two separate boot bugs.

4. **Repository hygiene is a CI category.** The frontend TS2307s and the five
   worker test failures were the same bug class: *exists locally, not on the
   runner* — one swallowed by a gitignore, one by a gate that never fetched its
   inputs. Both are now structural (tracked files, gated artifacts).

## Validations

- `scripts/verify_all.sh` — **all 9 gates passed** (136 passed / 3 deselected,
  golden 3 passed, e2e smoke 15.5s, "All gates passed").
- `npx tsc --noEmit --incremental false` + eslint: **clean** after the lib
  re-include.
- `actionlint`: clean on both workflows; `docker compose ... config`: clean.
- `ruff`: clean; `mypy` (scoped): baseline preserved, clean on touched files.
- **CI on GitHub**: fast gate green on `0bed033`, full gate green on the PR and
  on the `main` post-merge push (`9a10c46`).
- **Weights release live**: `weights-v1`, asset `n2n_unet_best_weights04.keras`
  (93,651,569 B), sha256
  `e401edaef9929692d3077a13fb4b6424436491e594155c9a7f8b0fc4ef7e2871`, download
  URL returns 200; both workflows download+verify against it.

## What I Learned

- A bare `lib/` entry in a repo-root `.gitignore` ignores `lib` directories at
  *any* depth — including `frontend/src/lib` and `frontend/e2e/lib`. It can
  never reproduce locally and only surfaces on a fresh checkout.
- Compose resolves relative bind sources against the compose file's directory,
  not the CWD — `../` from `deploy/` was one level too shallow.
- GitHub asset names are aggressively sanitized on upload; a downloader must
  pin the sanitized name, and uploaders should never use spaces/parens.
- `gh auth login --with-token` requires the `read:org` scope; the stored git
  credential from `git credential fill` works for REST API calls without it.
- The "golden" local setup masks artifact gaps — every gate input must be
  provably present on the runner, not assumed.

## Remaining Technical Debt

- `gh` CLI is installed (2.97.0) but not authenticated locally; API work goes
  through the stored git credential.
- The `weights-v1` tag points at pre-merge `main` (`80e688d`); fine for a pinned
  artifact, worth a comment in ADR-011 if it matters.
- Legacy local `master` branch remains (stale); active workflow is `main`.
- GHCR image registry deliberately deferred in ADR-011 — **reversed in Sprint
  4D** (ADR-016), which also re-tags this sprint's release seam.

## Ready for Sprint 4D?

**Yes.** CI/CD is real (both gates green on the merged tree), the weights
distribution seam is live and verified, and the deployment stack boots cleanly
end-to-end. Sprint 4D (production deployment architecture, ADR-012–017, GHCR)
can proceed from a clean `main`.

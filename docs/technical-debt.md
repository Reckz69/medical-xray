# Technical Debt Register

Accepted technical debt, tracked so it is a conscious decision rather than a
silent omission. Each entry records what is deferred, why, how to reproduce,
and the rule for paying it down. Per `docs/AI_ENGINEERING_GUIDE.md`, debt must
never block feature work — entries here are explicit, prioritized follow-ups.

## Repo-wide mypy typing pass

- **Status:** Open — deferred to a dedicated typing sprint. Must not block
  feature development or sprint completion (Sprint 4B decision).
- **What:** `backend/mypy.ini` is deliberately scoped to 18 source files
  (`follow_imports = skip` + an explicit `files =` list) so legacy / frozen
  modules (`# LEGACY - FROZEN`) and tests do not gate each sprint. Passing
  `backend/` as a mypy argument checks the whole tree instead.
- **Why deferred:** a repo-wide pass is a separate, later effort; the sprint
  gate (scoped) is clean, and the outstanding errors are union-attr noise in
  tests, return-type mismatches in a frozen legacy API, and untyped legacy
  worker modules — none of which change runtime behavior.
- **Reproduce:**
  ```sh
  cd backend && ./.venv/bin/python -m mypy --config-file mypy.ini backend/
  ```
- **Baseline (2026-08-07, after Sprint 4B):** 53 errors in 13 files
  (was 54 in 14; `gateway/main.py` fixed in 4B — `storage.bucket` is not on
  the `StorageProvider` ABC, use `settings.s3_bucket`).

  | File | Errors | Notes |
  | --- | --- | --- |
  | `tests/test_scheduler.py` | 26 | `union-attr` on `Job \| None`, cleanup fakes |
  | `tests/test_worker.py` | 10 | `union-attr` on `Job \| None` / `Object \| None` |
  | `worker/model_manager.py` | 3 | untyped legacy module |
  | `inference_engine.py` | 3 | `# LEGACY - FROZEN` |
  | `tests/test_preprocess.py` | 2 | |
  | `test_api.py` | 2 | `# LEGACY - FROZEN` |
  | `worker/preprocess.py` | 1 | untyped legacy module |
  | `worker/converters.py` | 1 | untyped legacy module |
  | `tests/test_postprocess.py` | 1 | |
  | `tests/test_observability.py` | 1 | generator return type `[misc]` |
  | `tests/test_converters.py` | 1 | |
  | `tests/golden/test_golden_enhancement.py` | 1 | |
  | `scripts/benchmark_cpu.py` | 1 | |

- **Pay-down rule:** after any fix, re-run the command above and update the
  baseline table so the entry always reflects reality.

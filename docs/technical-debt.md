# Technical Debt Register

Accepted technical debt, tracked so it is a conscious decision rather than a
silent omission. Per `docs/AI_ENGINEERING_GUIDE.md`, debt must never block
feature work — entries here are explicit, prioritized follow-ups.

Debt is tracked in two categories, by how urgently it must be paid:

## Category A — Correctness debt (fix immediately)

Invalid abstraction usage, missing invariants, impossible states, and potential
runtime crashes. New Category A items are fixed on the spot, never scheduled.

Resolved examples (the policy's provenance):

- **`gateway/main.py` startup logged `storage.bucket`, which is not on the
  `StorageProvider` ABC** (Sprint 4B). Fixed: log `settings.s3_bucket` — the
  value the MinIO provider actually uses. Also removed the last full-repo mypy
  error in a scoped file.
- **`worker/model_manager.py` dereferenced `self._pipeline.inputs/.outputs`
  without proving it was loaded** (Sprint 4B). Keras types `load_model()` as
  `Model | None`; `load_model` either returns a model or raises, but the code
  never said so. Fixed with `assert self._pipeline is not None` after load —
  documents the runtime invariant, fails fast if initialization is ever
  changed, and narrows the type for the shape check.
- **Scheduler retry tests were order/history-dependent** (Sprint 4C). The
  flake was a shared-state bug, not a timing race: `republish_retries` /
  `recover_stalled` count *every* due `RETRYING` row in the persistent `jobs`
  table, and six tests assert those global counts — rows left by earlier runs
  made the suite order- and history-dependent. Fixed with an autouse
  `DELETE FROM jobs` fixture in `tests/test_scheduler.py` (safe because `jobs`
  is a leaf table), making the counts deterministic. Root cause, fixed by test
  isolation — the assertions were not weakened.

Rule: if a Category A item is found, fix it in the same session — do not add it
to this register as "open".

## Category B — Typing debt (scheduled)

Optional/missing type coverage that does not affect runtime behavior. Tracked
and scheduled; must not interrupt feature delivery. Sub-buckets:

- TensorFlow has no type stubs (every `import tensorflow` is `Any`; not fixable
  without stubs — do not fight the TF typing ecosystem).
- NumPy stub limitations (e.g. `np.uint8(arr)` typed as `unsignedinteger` even
  though it returns an ndarray at runtime).
- Optional inference in tests (`Job | None` from ORM `.first()` calls; fixtures
  and mocks intentionally violate types).
- `# LEGACY - FROZEN` modules (`inference_engine.py`, `test_api.py`) pending
  removal.

**What:** `backend/mypy.ini` is deliberately scoped to 18 source files
(`follow_imports = skip` + an explicit `files =` list) so legacy / frozen
modules and tests do not gate each sprint. Passing `backend/` as a mypy
argument checks the whole tree instead.

**Reproduce:**
```sh
cd backend && ./.venv/bin/python -m mypy --config-file mypy.ini backend/
```

**Baseline (2026-08-07, after Sprint 4B):** 51 errors in 13 files.

| File | Errors | Notes |
| --- | --- | --- |
| `tests/test_scheduler.py` | 26 | `union-attr` on `Job \| None`, cleanup fakes |
| `tests/test_worker.py` | 10 | `union-attr` on `Job \| None` / `Object \| None` |
| `inference_engine.py` | 3 | `# LEGACY - FROZEN` (1 TF stubs, 1 return type, 1 annotation) |
| `worker/model_manager.py` | 1 | TF stubs only (`assert` fix removed the 2 `None`-derefs) |
| `tests/test_preprocess.py` | 2 | |
| `test_api.py` | 2 | `# LEGACY - FROZEN` (annotations) |
| `worker/preprocess.py` | 1 | annotation |
| `worker/converters.py` | 1 | NumPy stub limitation (return type) |
| `tests/test_postprocess.py` | 1 | |
| `tests/test_observability.py` | 1 | generator return type `[misc]` |
| `tests/test_converters.py` | 1 | |
| `tests/golden/test_golden_enhancement.py` | 1 | |
| `scripts/benchmark_cpu.py` | 1 | TF stubs |

**Pay-down rule:** after any fix, re-run the command above and update the
baseline table so the entry always reflects reality.

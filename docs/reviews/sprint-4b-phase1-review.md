# Sprint 4B — Phase 1 Review: Observability facade + structured logging

- **Status:** Review-complete, ready to commit
- **Date:** 2026-08-07
- **Branch:** `sprint/3-real-ml` (commit after this review)
- **Related:** [ADR-010](../adr/ADR-010-observability.md) (drafted in Phase 5), `docs/AI_ENGINEERING_GUIDE.md`

## Goal

Land the single observability facade (`gateway/core/observability/`) and switch
every process entry point to structured JSON logging with correlation context.
This is the foundation every later 4B phase (Prometheus metrics, OTel tracing)
builds on, so the disabled-mode contract and the "one abstraction per gate"
rule are the load-bearing decisions here.

## Files Changed

| File | Change |
| --- | --- |
| `backend/gateway/core/observability/__init__.py` | New — facade surface: `init_observability`, `configure_logging`, `log_context`, `metrics`, `tracer`. |
| `backend/gateway/core/observability/logging.py` | New — `JsonFormatter`, `set_correlation`, `log_context`, `get_correlation`. |
| `backend/gateway/core/observability/metrics.py` | New — `MetricsFacade` (lazy, no-op when disabled). |
| `backend/gateway/core/observability/tracing.py` | New — `TracerFacade.span()` (nullcontext when disabled). |
| `backend/gateway/core/observability/bootstrap.py` | New — `init_observability(service, log_level, otel_enabled, metrics_enabled)`. |
| `backend/gateway/core/logging.py` | **Deleted** — superseded by the facade package. |
| `backend/gateway/core/config.py` | Add `otel_enabled: bool = False` under an Observability section. |
| `backend/gateway/core/otel.py` | `TraceIDMiddleware` wraps the request in `log_context(trace_id, request_id)`; ASGI types corrected. |
| `backend/gateway/core/deps.py` | `get_current_user` sets `user_id` into the correlation context after auth. |
| `backend/gateway/main.py` | Lifespan calls `init_observability(service="gateway", ...)`. |
| `backend/worker/main.py` | `init_observability(service="worker")`; `_on_message` wraps the handler in `log_context(trace_id, scan_id, job_id)`. |
| `backend/scheduler/main.py` | `init_observability(service="scheduler")`; each cycle wrapped in `log_context(trace_id=uuid4)` so a cycle's lines correlate. |
| `backend/tests/test_observability.py` | New — 13 tests for the facade contract, formatter, and middleware. |
| `backend/mypy.ini` | New — minimal mypy config scoped to Phase 1 modules (`follow_imports = skip`). |
| `docs/AI_ENGINEERING_GUIDE.md` | Extended the existing engineering contract (no duplicate guidelines file): facade-only observability access, no-op contract, dependency justification rule, one abstraction per gate, per-phase review template, deployability rule. |

## Architecture Decisions

1. **One facade package owns logging + metrics + tracing.** Business code
   imports only `from gateway.core.observability import tracer, metrics, log_context`.
   Swapping Prometheus/OTel/Jaeger later touches only this package (ADR-010).
   Placed under `gateway/core/` because all three services (gateway, worker,
   scheduler) import from the gateway package already — it is the shared
   library, not a gateway-only concern.

2. **Disabled-mode no-op contract is non-negotiable.** `otel_enabled=False`
   (the default) makes `tracer.span()` a `contextlib.nullcontext()` and every
   metric a `NoopInstrument`. Call sites need zero `if enabled` branching, so
   observability is removable without touching business code.

3. **Correlation lives in a `ContextVar`** so each async task / message handler
   carries its own context. `log_context` is a context manager that restores
   the prior context on exit (worker handlers, scheduler cycles, middleware);
   `set_correlation` merges task-scoped values (user_id after auth). Never
   mutated in place — always replaced, so nested scopes restore correctly.

4. **`trace_id`/`span_id` prefer the active OTel span** when tracing is on,
   otherwise fall back to the gateway's `TraceIDMiddleware` correlation value.
   This keeps Phase 1 logs correlated without the SDK.

5. **No new runtime dependencies in Phase 1.** The facade is pure stdlib
   (`contextvars`, `json`, `logging`). Prometheus/OTel land in Phases 2/3 with
   written justification per the engineering contract.

6. **Engineering guidelines extended, not duplicated.** The plan called for a
   new `docs/engineering/ai-development-guidelines.md`, but
   `docs/AI_ENGINEERING_GUIDE.md` already is the engineering contract (DoD,
   ruff/mypy gates, explain-everything rule). A second file would fragment the
   rules; the existing guide was extended with the observability-era rules.

## Tests Added (13)

- JsonFormatter: valid JSON, message/level/logger/timestamp fields, correlation
  fields present only when set.
- `log_context`: nested merge, restore-on-exit, empty/None values ignored.
- `set_correlation`: merge + persist; empty values ignored.
- `tracer` no-op: sync + async span usage compile and run; context is
  `(None, None)` when disabled.
- `metrics` no-op: all instruments are `NoopInstrument` when disabled.
- `TraceIDMiddleware`: stamps `trace_id`/`request_id` into the correlation
  context for the request; bridges a caller-supplied `X-Request-ID`.
- Autouse fixture resets the correlation `ContextVar` per test (tests share the
  session-scoped event loop, so state would otherwise leak).

## Ruff / MyPy

- `ruff check` on all Phase 1 files: **clean**.
- `mypy` (scoped to Phase 1 modules, `follow_imports = skip` for legacy
  dependencies): **clean**.
- Pre-existing ruff violations in frozen legacy modules
  (`backend/main.py`, `backend/test_api.py`, `inference_engine.py`, alembic
  versions) are untouched and out of scope.

## Performance Impact

No measurable impact. Disabled-mode overhead is one `ContextVar.get()` copy per
log record; entry-point wiring adds no per-request work beyond the middleware
`log_context` (a dict copy on request enter/exit). The pre-phase-4 performance
gate (tracing OFF vs ON, upload + inference latency, < 5%) is still pending and
will be reported in `docs/benchmarks/observability-overhead.md`.

## What I Learned

- **A sync test that calls `asyncio.run()` breaks pytest-asyncio's session
  loop**: it tore down the shared loop and cascaded ~45 unrelated failures
  into later async tests ("no current event loop"). Converting the test to an
  async test fixed it. The suite is green only when tests run on the loop
  pytest-asyncio owns.
- **Dev processes interfere with the integration suite**: the running gateway /
  worker / scheduler were consuming RabbitMQ messages that the tests depend
  on, producing flaky, randomly-varying failures. Stopping them (per the plan's
  own note) restored a fully green suite: **122 passed, 3 deselected**.
- **`ContextVar` defaults must be immutable** (ruff B039): the `default={}`
  form is replaced by `default=None` with `dict(get() or {})` — same semantics,
  no shared-mutable pitfall.

## Remaining Technical Debt

- Metrics and tracing facades are placeholders; real Prometheus instruments
  (Phase 2) and OTel SDK wiring (Phase 3) are still pending.
- `mypy` is scoped to Phase 1 modules with `follow_imports = skip`; a
  repo-wide typing pass (legacy frozen modules, `job_repository`,
  `model_manager`, `converters`) is a separate, later effort.
- Pre-existing ruff violations in frozen legacy modules remain.
- Phase 2/3 will add `prometheus-client` + `opentelemetry-*` deps with
  justification; the facade contract means business code will not change.

## Ready for Phase 2?

**Yes.** The facade contract is proven by tests, ruff + mypy are clean, and the
full integration suite is green (122 passed, 3 deselected) with the dev stack
stopped. Phase 2 (real Prometheus instruments + `/metrics` exposure) can build
on `MetricsFacade._build()` without touching business call sites.

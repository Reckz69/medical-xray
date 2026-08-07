# Sprint 4B — Phase 2 Review: Prometheus metrics + `/metrics` exposure

- **Status:** Review-complete, ready to commit
- **Date:** 2026-08-07
- **Branch:** `sprint/3-real-ml` (commit after this review)
- **Related:** [ADR-010](../adr/ADR-010-observability.md) (drafted in Phase 5), `docs/AI_ENGINEERING_GUIDE.md`, `docs/reviews/sprint-4b-phase1-review.md`

## Goal

Turn the Phase 1 `MetricsFacade` placeholder into real Prometheus instruments and
scrape exposure, and instrument every agreed call site without breaking the
facade contract. Phase 2 delivers:

* 12 declared instruments (`_INSTRUMENT_SPECS`) materialised lazily per-process
  against a process-local `CollectorRegistry`.
* Gateway `/metrics` endpoint (app port) and worker/scheduler Prometheus HTTP
  server on `metrics_port` (:9101), matching the ADR-010 scrape map.
* Call-site instrumentation for gateway HTTP, scan upload, worker jobs, and the
  scheduler retry/cleanup loops — all through the facade, never Prometheus
  directly.
* `prometheus-client>=0.20.0` (the one direct Prometheus dependency, justified
  in `requirements.txt`).

## Files Changed

| File | Change |
| --- | --- |
| `backend/gateway/core/observability/metrics.py` | Rewrite Phase 2 — `NoopInstrument`, `InstrumentSpec`, `_INSTRUMENT_SPECS` (12 metrics), lazy `_build()` (Counter/Gauge/Histogram on a process-local registry, Noop fallback), `configure(enabled=...)` (rebuilds registry + registers `PROCESS_COLLECTOR`), `render()`, `start_server(port)`, `CONTENT_TYPE_LATEST`. |
| `backend/gateway/core/config.py` | Add `metrics_enabled: bool = False` and `metrics_port: int = 9101` under the Observability section. |
| `backend/gateway/main.py` | `MetricsMiddleware` (HTTP request counter + latency histogram, no-op when disabled); flag-gated `GET /metrics` returning `metrics.render()` with the facade's media type; `metrics_enabled` wired into `init_observability`. |
| `backend/worker/main.py` | `metrics_enabled` wired; `metrics.start_server(settings.metrics_port)` when enabled. |
| `backend/scheduler/main.py` | `obs_metrics` alias for the facade (avoids the `scheduler.metrics.metrics` collision); `metrics_enabled` wired; `obs_metrics.start_server(settings.metrics_port)` when enabled. |
| `backend/gateway/domains/scans/service.py` | `scan_upload_seconds` histogram around the persist section (object upload → rows → commit); dedup paths excluded. |
| `backend/worker/executor.py` | `worker_job_duration_seconds` (message in → job done, `try/finally`); `worker_inference_seconds` / `worker_processing_seconds` from `StageTimings`; `worker_job_failures_total` on terminal FAILED. |
| `backend/scheduler/retry_jobs.py` | `scheduler_jobs_republished_total` on every confirmed republish; per-cycle `jobs_by_status{status}` gauge from `JobRepository.count_by_status()` (all statuses zeroed first, then set — no stale values). |
| `backend/scheduler/cleanup.py` | `scheduler_cleanup_duration_seconds` (gauge), `scheduler_cleanup_failures_total` and `scheduler_cleanup_skipped_total` (counters) mirroring the existing in-process `SchedulerMetrics` fields. |
| `backend/gateway/repositories/job_repository.py` | Add `count_by_status()` (GROUP BY query) for the per-cycle gauge. |
| `backend/tests/test_observability.py` | Extend to 18 tests — enabled-mode materialisation, render output, unknown-name no-op, registry reset, `MetricsMiddleware` recording. |
| `backend/mypy.ini` | Add the Phase 2 instrumented call sites to the scoped module list. |
| `backend/requirements.txt` | Add `prometheus-client>=0.20.0` with a written justification comment. |

## Architecture Decisions

1. **One spec set drives every instrument.** `_INSTRUMENT_SPECS` is the single
   place instrument metadata (name → kind/help/labels) lives. The facade
   materialises Counter/Gauge/Histogram lazily against a process-local
   `CollectorRegistry`, so each process only creates the instruments it touches
   and one process's scrape surface never leaks into another's. Adding a metric
   is a one-line spec + a call site; nothing else changes.

2. **Disabled-mode contract holds in Phase 2.** Disabled processes still route
   every call through `metrics.*`; the facade returns `NoopInstrument`, and
   `render()` on the empty registry returns `b""`. No business call site gained
   an `if enabled` branch. `MetricsMiddleware` runs unconditionally — when
   metrics are off it measures but records nothing.

3. **Three exposure shapes, one facade.** Gateway serves `/metrics` on the app
   port (FastAPI route). Worker and scheduler run `start_http_server` on
   `metrics_port` (:9101) because they are not HTTP services. All three call
   `metrics.render()` / `metrics.start_server()` — the Prometheus HTTP plumbing
   stays behind the facade (even the `Content-Type` constant is `metrics.
   CONTENT_TYPE_LATEST`, so `gateway/main.py` never imports prometheus_client).

4. **Re-`configure` rebuilds the registry.** Tests and re-bootstrap get a clean
   scrape surface; instruments are never shared across enables.

5. **Gauge semantics: zero-then-set.** `jobs_by_status` is a per-cycle GROUP BY;
   every known status is zeroed before the DB counts are applied so a status
   that has no jobs this cycle does not keep a stale value.

6. **Cleanup mirrors the in-process counters.** The scheduler already keeps
   `SchedulerMetrics` for its run reports and tests; the Prometheus counters are
   incremented at the same points, so the two views cannot diverge.

## Tests Added (5, total 18)

- `test_metrics_enabled_materializes_real_instruments` — counter/label + gauge +
  histogram recorded, then verified in `render()` text (sample values and HELP
  lines).
- `test_metrics_render_lists_every_declared_instrument_when_enabled` — touching
  each of the 12 specs materialises it; `# HELP <name>` present in the output.
- `test_metrics_unknown_instrument_is_noop_when_enabled` — unknown names stay
  no-ops even with metrics on.
- `test_metrics_reconfigure_resets_registry` — after `configure(False)` the
  registry is empty (`render() == b""`) and instruments are no-ops again.
- `test_metrics_middleware_records_http_request` — a request through
  `MetricsMiddleware` yields `http_requests_total{method="GET",status="200"} 1.0`
  and histogram buckets.

Every enabled-mode test resets `configure(enabled=False)` in a `finally`, so the
shared facade never leaks enabled state into other tests.

## Ruff / MyPy

- `ruff check` on all changed files: **clean** (two pre-existing isort issues in
  `metrics.py`/`job_repository.py` import blocks auto-fixed).
- `mypy` (scoped, `follow_imports = skip`): **clean — 16 source files**.
- The facade contract means the only new direct dependency
  (`prometheus-client`) is imported in exactly one file.

## Performance Impact

Enabled-mode call-site cost is one `perf_counter()` + instrument record per
observation (a counter increment or a histogram `observe`) — nanoseconds per
call. The gateway middleware adds a `perf_counter()` around the request; when
metrics are disabled it is a no-op measurement. The pre-phase-4 performance gate
(tracing OFF vs ON, < 5%) remains pending and will be reported in
`docs/benchmarks/observability-overhead.md`.

## What I Learned

- **The facade's `__getattr__` is permissive by design, and it stays behind the
  `_` guard.** Non-underscore unknown names return a Noop, which is what makes
  instrumented call sites compile even before a spec is added — but it also
  means a typo in a metric name silently records nothing. Mitigation: the spec
  list + the "render lists every declared instrument" test pin the exact names.
- **`prometheus-client` has no `__version__`** in the installed wheel; verifying
  the install needs `prometheus_client.__file__`.
- **Re-running `configure(False)` leaves `render()` empty**, which is exactly
  the removable-observability guarantee — good enough to assert directly in a
  test.

## Remaining Technical Debt

- Phase 3 (OTel tracing + Collector/Jaeger) and the performance gate are next.
- The per-cycle `jobs_by_status` gauge is set by the scheduler's `run_once`; a
  multi-scheduler deployment writes the same gauge from each process, which is
  correct for a fleet-level view but will be noted when the scrape setup lands.
- `mypy` stays scoped to the facade + entry points + instrumented call sites;
  a repo-wide typing pass is a separate, later effort.

## Ready for Phase 3?

**Yes.** The facade now serves real Prometheus instruments through a single
surface, all agreed call sites are instrumented, ruff + mypy are clean, and the
full integration suite is green (**127 passed, 3 deselected**) with the dev stack
stopped. Phase 3 (OTel tracing) can build on `TracerFacade.span()` without
touching any of the Phase 2 call sites.

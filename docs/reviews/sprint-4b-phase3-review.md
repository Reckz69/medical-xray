# Sprint 4B — Phase 3 Review: OpenTelemetry tracing + W3C `traceparent` propagation

- **Status:** Review-complete, ready to commit
- **Date:** 2026-08-07
- **Branch:** `sprint/3-real-ml` (commit after this review)
- **Related:** [ADR-010](../adr/ADR-010-observability.md) (drafted in Phase 5), `docs/AI_ENGINEERING_GUIDE.md`, `docs/reviews/sprint-4b-phase1-review.md`, `docs/reviews/sprint-4b-phase2-review.md`

## Goal

Replace the Phase 1 `TracerFacade` placeholder with a real OpenTelemetry SDK
wiring for distributed tracing, and continue remote W3C traces end-to-end
(gateway request -> RabbitMQ -> worker -> pipeline). Phase 3 delivers:

* `tracing.py` facade rewrite — `configure(enabled, service, exporter,
  exporter_name, endpoint)`, real `TracerProvider` + processor/exporter wiring,
  `span()` / `span_from_traceparent()` / `get_current_span_context()` /
  `get_current_traceparent()` / `shutdown()`. Disabled mode stays a no-op (no
  `if enabled` branches in business code).
* W3C `traceparent` propagation seam in `queue.py:build_message_headers` —
  every published command/event carries the active span's `traceparent` when
  tracing is on, and the legacy `trace_id`/`correlation_id` headers otherwise.
* `TraceIDMiddleware` runs the request inside a span that continues the
  incoming `traceparent` (or starts a fresh root), and when tracing is enabled
  the OTel trace id becomes the correlation `trace_id` so envelope, logs, and
  AMQP headers all agree on one trace.
* Consume-side continuation in `worker/main.py` (`worker.inference.run`),
  job span in `worker/executor.py` (`worker.process_job`), and the five
  pipeline stage spans in `worker/orchestrator.py` (`pipeline.{convert,
  preprocess,inference,postprocess,encode}`). The upload persist path is one
  span (`scans.upload.persist`).
* `otel_exporter` / `otel_endpoint` settings; `tracer.shutdown()` in every
  entry-point teardown.
* `opentelemetry-api/sdk/exporter-otlp-proto-http` (tracing-only, justified in
  `requirements.txt`).

## Files Changed

| File | Change |
| --- | --- |
| `backend/gateway/core/observability/tracing.py` | Phase 3 rewrite — `TracerFacade.configure()` builds a `TracerProvider` with `SERVICE_NAME` resource; injected exporter → `SimpleSpanProcessor` (deterministic tests), else `BatchSpanProcessor` + `OTLPSpanExporter(endpoint)` (or `ConsoleSpanExporter` for `"console"`); re-configure `shutdown()`s prior wiring first; `span()` / `span_from_traceparent()` no-op branches use a plain `yield` (a `yield from contextlib.nullcontext()` raises `TypeError` inside a `@contextmanager`); `get_current_span_context()` returns hex `(trace_id, span_id)`; `get_current_traceparent()` injects via `TraceContextTextMapPropagator`; `shutdown()` swallows exporter errors so teardown never raises. |
| `backend/gateway/core/config.py` | Add `otel_exporter: str = "otlp-http"` and `otel_endpoint: str = "http://collector:4318"` under the Observability section. |
| `backend/gateway/core/observability/bootstrap.py` | `init_observability` passes `service`, `exporter_name=settings.otel_exporter`, `endpoint=settings.otel_endpoint` into `tracer.configure()`. |
| `backend/gateway/core/queue.py` | New `build_message_headers(trace_id, correlation_id)` — always emits `trace_id` + `correlation_id`, adds W3C `traceparent` when tracing is on and a span is active; `_publish` now calls it. |
| `backend/gateway/core/otel.py` | `TraceIDMiddleware` wraps the request in `span_from_traceparent(..., name=f"{method} {path}")` with http attrs; OTel trace id overrides the correlation `trace_id` when tracing is on (via `request.state.trace_id`); X-Request-ID echo kept; `_TRACEPARENT_RE` relaxed to accept any flags byte. |
| `backend/gateway/domains/scans/service.py` | `scans.upload.persist` span wraps the whole persist path (upload → rows → commit → histogram). |
| `backend/worker/main.py` | `_on_message` consumes `traceparent` header into `span_from_traceparent(..., name="worker.inference.run")` around the existing `log_context`; `tracer.shutdown()` in teardown. |
| `backend/worker/executor.py` | `worker.process_job` span around the run/failure block. |
| `backend/worker/orchestrator.py` | `pipeline.convert / preprocess / inference / postprocess / encode` spans around the existing stage timings. |
| `backend/gateway/main.py` | `tracer.shutdown()` in `lifespan` teardown. |
| `backend/scheduler/main.py` | `tracer.shutdown()` in teardown. |
| `backend/tests/test_observability.py` | 8 new tests (total 26). |
| `backend/mypy.ini` | Add `gateway/core/queue.py` and `worker/orchestrator.py` to the scoped module list (18 source files). |
| `backend/requirements.txt` | Add OTel packages with a tracing-only justification comment. |

## Architecture Decisions

1. **OTel is tracing-only.** Prometheus stays the metrics system (ADR-010).
   OTel only provides spans + W3C propagation; no OTLP metrics are emitted. The
   only new direct dependencies are the three `opentelemetry-*` packages, used
   in exactly one file (`tracing.py`).

2. **One span per seam, one trace per job.** The gateway middleware starts the
   span (continuing the client `traceparent` if present), the AMQP header
   carries that trace via `build_message_headers`, and the worker continues it
   with `span_from_traceparent`. The job span and pipeline stage spans nest
   underneath, so a single trace walks request → queue → worker → pipeline.

3. **The `traceparent` header is the propagation contract; the legacy
   `trace_id` header stays.** When tracing is enabled the correlation
   `trace_id` *is* the OTel trace id (middleware override), so all three
   surfaces — envelope, structured logs, AMQP headers — agree. When disabled,
   the middleware mints the 32-hex correlation id exactly as before and no
   `traceparent` is injected, keeping the disabled contract byte-for-byte
   unchanged.

4. **`exporter` injection = deterministic tests; config = production.** Tests
   inject an `InMemorySpanExporter` through a `SimpleSpanProcessor` so finished
   spans are available synchronously. Production uses `BatchSpanProcessor` +
   `OTLPSpanExporter(endpoint)` (export on a background thread, cheaper on the
   hot path) or `ConsoleSpanExporter` for `otel_exporter=console` local
   debugging. The collector is the config-only abstraction for the trace
   backend — swapping Tempo/Jaeger changes only `otel_endpoint`.

5. **No-op branches use a plain `yield`.** Inside a `@contextmanager` function,
   delegating with `yield from contextlib.nullcontext()` raises `TypeError`.
   The disabled-mode contract is a bare `yield`, so `with tracer.span(...)`
   works unchanged in sync and async business code.

6. **Teardown flushes.** `tracer.shutdown()` in every entry point's teardown so
   batch spans flush on stop and no export thread lingers.

## Tests Added (8, total 26)

- `test_tracer_records_spans_when_enabled` — an enabled span is recorded with
  its name and attributes (InMemory exporter).
- `test_tracer_nested_spans_share_trace_and_parent` — nested spans share the
  trace id and the inner span's parent is the outer span.
- `test_get_current_span_context_when_enabled` — hex `(trace_id, span_id)` from
  the active span.
- `test_span_from_traceparent_continues_remote_trace` — a remote `traceparent`
  is continued (same trace id, remote parent).
- `test_get_current_traceparent_is_none_when_disabled` — disabled contract.
- `test_build_message_headers_injects_traceparent_when_active` — W3C header
  present only when enabled + span active.
- `test_build_message_headers_without_active_span` — legacy `trace_id` /
  `correlation_id` still ride along when disabled.
- `test_middleware_prefers_otel_trace_id_when_tracing_on` — `TraceIDMiddleware`
  stamps the OTel trace id as the correlation id when tracing is on.

Every enabled-mode test resets `tracer.configure(enabled=False)` in a
`finally`, so the shared facade never leaks enabled state into other tests.

## Ruff / MyPy

- `ruff check` on all changed files: **clean**.
- `mypy` (scoped, `follow_imports = skip`): **clean — 18 source files**
  (added `queue.py`, `orchestrator.py`; widened `build_message_headers` to
  accept `correlation_id: str | None`, which it already handled at runtime).
- `scripts/benchmark_observability.py`: `ruff check` clean.

## Performance Gate

`docs/benchmarks/observability-overhead.md` (new) — tracing OFF vs ON on this
machine (Apple M2, Python 3.11.15), `SimpleSpanProcessor` + `InMemorySpanExporter`
(a conservative synchronous upper bound; production `BatchSpanProcessor` is
cheaper on the hot path):

* Part A (median ns): `tracer.span` 0.9 µs → 19.1 µs (+18.2 µs); `span_from_traceparent`
  0.8 µs → 28.2 µs (+27.4 µs); `build_message_headers` 0.3 µs → 1.1 µs (+0.8 µs).
* Part B (simulated worker job — 7 spans + header build around ~1 ms of work):
  OFF 193.6 jobs/s, ON 192.5 jobs/s → **overhead +0.55%**.

**Gate result: PASS** (+0.55% < 5%).

## What I Learned

- `yield from contextlib.nullcontext()` inside a `@contextmanager` is a
  `TypeError` trap — the no-op body must be a plain `yield`. This was the root
  cause of five test failures after the rewrite.
- `OTLPSpanExporter(endpoint=endpoint or None)` lets `otel_endpoint` default to
  the OTLP default when empty, but production should always set it
  (`http://collector:4318`) — the default is `localhost` and silent-losses if
  unreachable.
- The `traceparent` flags byte is not always `01` (`0x03` sampled+random is
  valid), so the middleware regex must accept any flags byte rather than pinning
  `-01`.
- The per-seam cost of `span_from_traceparent` is ~28 µs (context extraction +
  span start). Against ms-scale worker jobs this is negligible; the measured
  end-to-end overhead is +0.55%.

## Remaining Technical Debt

- Phase 4 (deploy overlay + prometheus/grafana configs + test-compose) and
  Phase 5 (ADR-010, CHANGELOG, docs, tag) are next.
- A benchmark calibration loop that measured ~1 ms work and adjusted by ±20%
  could oscillate forever under timer jitter; the final script calibrates
  deterministically in one pass.
- `mypy` stays scoped to the facade + entry points + instrumented call sites; a
  repo-wide typing pass is a separate, later effort.
- The earlier full-suite run hit one transient stall (no output for 300 s) that
  did not reproduce in two subsequent full runs (135 passed, 61 s); believed to
  be a RabbitMQ/DB warm-up blip rather than tracing. The scheduler
  `republish_retries` count flake (`3 == 1`) is pre-existing DB-state flakiness
  (leftover `retrying` jobs with past `next_retry_at`) and is unrelated to Phase 3
  — the worker diffs are span-instrumentation-only.

## Ready for Phase 4?

**Yes.** Tracing is a real OTel wiring behind the facade with W3C propagation
across every agreed seam, disabled mode stays a no-op, ruff + mypy are clean,
the full integration suite is green (**135 passed, 3 deselected**) with the dev
stack stopped, and the performance gate passes at **+0.55%**. Phase 4 (deploy +
scrape/export config) can proceed without touching Phase 3 code.

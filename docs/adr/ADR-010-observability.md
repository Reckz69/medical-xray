# ADR-010: Observability — tracing-only OTel, Prometheus metrics, removable overlay

- **Status:** Accepted
- **Date:** 2026-08-07
- **Deciders:** Architecture review
- **Related:** [ADR-009-scheduler.md](ADR-009-scheduler.md), `docs/AI_ENGINEERING_GUIDE.md`, `docs/reviews/sprint-4b-phase4-review.md`

## Context

Sprint 4B introduced observability across the gateway, worker, and scheduler:
structured JSON logging (Phase 1), a Prometheus metrics facade (Phase 2), and
OpenTelemetry tracing with W3C `traceparent` propagation end-to-end
(request → RabbitMQ → worker → pipeline, Phase 3). The deploy stack is an
optional overlay (Phase 4). This ADR records the decisions that shaped how the
three signals are produced, where they go, and how the app stays decoupled from
any specific vendor.

Three forces drove the design:

1. **The app must not depend on observability infrastructure.** A broken or
   absent collector/Prometheus must never take down the gateway. The stack runs
   with observability disabled by default and only wires it up when the overlay
   is explicitly requested.
2. **Business code must not import vendor SDKs.** Code reads
   `from gateway.core.observability import tracer, metrics, log_context` — never
   `opentelemetry.*` or `prometheus_client.*` directly. This keeps a future
   vendor swap to the facade.
3. **The trace backend is not chosen yet.** Jaeger, Grafana Tempo, and a managed
   vendor are all plausible; the collector is the stable seam.

## Decision

### Signals and their systems

- **Traces → OpenTelemetry SDK, tracing-only.** OTel provides spans + W3C
  `traceparent` propagation. No OTLP metrics are emitted. The only OTel direct
  dependency lives in one file (`tracing.py`).
- **Metrics → Prometheus client, no change to the architecture.** The gateway
  serves `/metrics` on the app port; the worker and scheduler each run a
  Prometheus HTTP server on `METRICS_PORT` (:9101). Prometheus scrapes all three
  by compose service DNS name.
- **Logs → structured JSON** (Phase 1). No Loki/Promtail in Sprint 4B; log
  shipping is deferred to Sprint 4C.

### The facade seam

`gateway/core/observability/` (logging, metrics, tracing) is the only place that
imports vendor SDKs. `configure()`/`enabled` state lives behind the facade; when
disabled, every facade call is a no-op, so business code needs no `if enabled`
branches. The trace id from the active OTel span becomes the correlation
`trace_id` so envelopes, structured logs, and AMQP headers agree on one trace.

### W3C propagation contract

`queue.py:build_message_headers` emits the active span's `traceparent` when
tracing is on, and the legacy `trace_id`/`correlation_id` otherwise. The worker
continues remote traces with `span_from_traceparent` — one trace per job across
every hop. The `traceparent` header is the propagation contract.

### The collector is the config-only trace backend

App nodes know only `http://otel-collector:4318` (OTLP/HTTP). The collector
currently exports to `debug` (stdout); forwarding to Tempo/Jaeger is a config
edit in `infrastructure/otel-collector/config.yaml`, zero app change. An OTel
exporter quirk was handled in the facade: an explicitly-passed OTLP endpoint is
used verbatim by the SDK (only the env-var default path gets `/v1/traces`
appended), so `_otlp_http_endpoint` normalizes a bare host:port — otherwise
every span 404s silently.

### Removable overlay

`backend/deploy/observability.yml` merges onto the base compose to add
otel-collector, prometheus, grafana and switch the app services onto tracing +
metrics. The core stack (`deploy/docker-compose.yml` alone) runs identically
without it. `deploy/docker-compose.test.yml` gates the app services behind the
`app` compose profile so the host-run pytest suite can never start a competing
app process.

## Rationale

- **One trace per job, propagated by header, not rebuilt:** continuing a remote
  `traceparent` across the AMQP seam is cheaper than re-rooting and keeps the
  whole journey — gateway request, queue hop, pipeline stages — under one trace
  id that also lands in `jobs`/`audit_logs` rows and every envelope.
- **Tracing-only OTel:** the metrics path was already Prometheus-shaped (Sprint
  2A `/metrics`), and adding OTLP metrics would duplicate exporters with zero
  user value. One signals-per-system split, two direct vendor deps (OTel for
  spans, prometheus_client for metrics), both quarantined in the facade.
- **Collector as abstraction:** the collector absorbs the "which backend"
  decision so the app never learns Tempo/Jaeger specifics and never re-exports
  on a backend change — a config swap in one file.
- **Overlay, not a merged stack:** keeps the core stack runnable in CI and local
  dev without three extra containers, honors "app never depends on optional
  observability infra," and keeps the observability additions reviewable as one
  self-contained change.
- **Facade no-op contract over `if enabled`:** the disabled path is
  byte-for-byte the pre-observability behavior; no business code branch means no
  way for a disabled-mode bug to corrupt the enabled path (and vice versa).

## Alternatives considered

- **OTLP metrics alongside tracing** — rejected: two metric pipelines (OTel +
  Prometheus) for the same data, more moving parts, no benefit.
- **Direct-to-Tempo/Jaeger exporters in the app** — rejected: pins the backend
  into app config; the collector keeps the swap a config-only change (ADR rule:
  the seam that may change most is abstracted first).
- **Hard-wiring the observability stack into the base compose** — rejected: the
  core stack must run without it (CI, minimal dev); overlay keeps it removable.
- **`if enabled` guards scattered through business code** — rejected: no-op
  facade keeps business code clean and the disabled contract identical.
- **Loki/Promtail for logs in 4B** — deferred to 4C; logs are already structured
  JSON, so shipping them later needs no code change.

## Consequences

**Positive**
- The full stack boots onto real tracing + metrics with one merged compose
  command; a smoke test proved spans reach a real collector (and caught a real
  silent-drop bug, now fixed + tested).
- Observability is removable: core stack, CI, and tests run with zero
  observability containers.
- Every span/metric/log surfaces one shared trace id end-to-end.
- Backend swap (Tempo/Jaeger) is a config edit; metric/lock/otel deps are
  quarantined behind the facade.

**Negative**
- The overlay adds three containers when enabled; operators must understand the
  overlay/`app`-profile compose arrangement.
- A `METRICS_PORT` HTTP server runs in the worker/scheduler when metrics are
  enabled — a small surface to firewall in prod.
- OTel exporter path handling is non-obvious (explicit endpoints are used
  verbatim); the facade's `_otlp_http_endpoint` + unit test pin the behavior.
- Grafana has a provisioned datasource but no dashboards yet (follow-up, not
  part of 4B).

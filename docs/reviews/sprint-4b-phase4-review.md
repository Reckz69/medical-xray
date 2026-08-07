# Sprint 4B — Phase 4 Review: observability deploy overlay + infra configs

- **Status:** Review-complete, ready to commit
- **Date:** 2026-08-07
- **Branch:** `sprint/3-real-ml` (commit after this review)
- **Related:** [ADR-010](../adr/ADR-010-observability.md) (drafted in Phase 5), `docs/AI_ENGINEERING_GUIDE.md`, `docs/reviews/sprint-4b-phase1-review.md`, `docs/reviews/sprint-4b-phase2-review.md`, `docs/reviews/sprint-4b-phase3-review.md`

## Goal

Ship the observability stack as a **removable deploy overlay** so the core
stack runs unchanged without it, and wire the running gateway/worker/scheduler
onto OTel tracing + Prometheus metrics with config that was validated against
the real binaries. Phase 4 delivers:

* `backend/deploy/observability.yml` — the overlay: OTel Collector (traces),
  Prometheus (scrape), Grafana (dashboards), plus the env overrides that switch
  the three app services onto OTel/HTTP tracing and Prometheus scraping.
* `backend/deploy/docker-compose.test.yml` — an infra-only override that gates
  the app services behind the `app` compose profile so the pytest suite brings
  up exactly the containers it hits on the host (no competing app process).
* `backend/infrastructure/otel-collector/config.yaml`, `prometheus/prometheus.yml`,
  and `grafana/provisioning/datasources/prometheus.yml` — the configs mounted
  into those containers, each validated against its real binary.
* A **real bug found and fixed by the deploy smoke test**: `OTLPSpanExporter`
  uses an explicitly-passed `endpoint` verbatim (only the env-var default path
  gets `/v1/traces` appended), so `http://otel-collector:4318` would POST to
  `/` → 404 → **every span silently dropped**. The facade now appends the
  signal path itself (`_otlp_http_endpoint`), guarded by a new unit test.

## Files Changed

| File | Change |
| --- | --- |
| `backend/deploy/observability.yml` | New overlay (merges with `docker-compose.yml`). Adds `otel-collector` (0.158.0, :4318), `prometheus` (v3.5.5, :9090, 15d retention), `grafana` (12.4.7, host :3001 to avoid the Next.js dev server on :3000, admin password from `GRAFANA_ADMIN_PASSWORD`). Overrides gateway/worker/scheduler env: `OTEL_ENABLED=true`, `OTEL_EXPORTER=otlp-http`, `OTEL_ENDPOINT=http://otel-collector:4318`, `METRICS_ENABLED=true`, and `METRICS_PORT=9101` on worker+scheduler. App services `depends_on` the collector with `service_started`. |
| `backend/deploy/docker-compose.test.yml` | New override that puts `profiles: ["app"]` on gateway/worker/scheduler. Merged `docker compose config --services` = minio, minio-init, postgres, rabbitmq, redis only — infra-only bring-up for the host-run pytest suite. |
| `backend/infrastructure/otel-collector/config.yaml` | Collector: OTLP/HTTP receiver (:4318) → `batch` → `debug` exporter (stdout). Header comment documents the Tempo swap (config-only backend abstraction). |
| `backend/infrastructure/prometheus/prometheus.yml` | Scrape config: gateway `gateway:8000/metrics`, worker `worker:9101`, scheduler `scheduler:9101`, 15 s interval. Targets are service DNS names, not host ports, so placement stays correct. |
| `backend/infrastructure/grafana/provisioning/datasources/prometheus.yml` | Provisioned Prometheus datasource (`http://prometheus:9090`, default, editable). |
| `backend/gateway/core/observability/tracing.py` | Deploy-caught fix: `_default_exporter` builds `OTLPSpanExporter(endpoint=_otlp_http_endpoint(endpoint) or None)`; new module-level `_otlp_http_endpoint()` appends `/v1/traces` when the path is empty or `/` (else returns unchanged; empty input → empty). |
| `backend/tests/test_observability.py` | New `test_otlp_http_endpoint_appends_signal_path` (bare host, trailing `/`, explicit path, empty). Total 27 tests. |

No `backend/README.md` exists in `deploy/`, so operator usage lives in the
compose-file headers, this review, and the Phase 5 docs
(`system-architecture.md`, `docs/README.md`) rather than a new doc file.

## Architecture Decisions

1. **Observability is a removable overlay.** `observability.yml` is a second
   compose file merged only when explicitly requested. The core stack (base
   `docker-compose.yml`) runs identically without it, satisfying
   `docs/AI_ENGINEERING_GUIDE.md` — the app never depends on optional
   observability infra. The smoke test verified both directions: full stack
   with the overlay up, and the core stack without it.

2. **The collector is the config-only trace backend.** App nodes only know
   `http://otel-collector:4318`. The collector currently exports to `debug`
   (stdout) so an end-to-end span path is visible in `docker compose logs`;
   forwarding to Tempo/Jaeger is a config edit in one file, zero app change
   (ADR-010).

3. **Service DNS names, not host ports, for scrape targets.** Prometheus scrapes
   `gateway:8000`, `worker:9101`, `scheduler:9101` on the compose network —
   correct regardless of container placement (ADR-010 scrape map). Only user
   entry points (collector :4318, Prometheus :9090, Grafana :3001) are published
   to the host.

4. **Test suite gets an infra-only override.** The pytest integration suite runs
   on the host against containers (postgres :5433, redis :6379, rabbitmq :5672,
   minio :9000/9001). Gating the app services behind `profiles: ["app"]` means a
   bare `docker compose ... up -d` can never start a competing gateway/worker/
   scheduler while the suite runs — a hard guarantee, not a remember-to-stop
   convention.

5. **The exporter fix belongs to the facade, not the config.** Rather than
   teaching every deployment to spell out `http://collector:4318/v1/traces`,
   `_otlp_http_endpoint` normalizes any user-supplied endpoint inside
   `tracing.py`. A unit test pins the contract; the smoke test proved it against
   a real collector.

## Validations (all run against the real tools)

- `docker compose -f docker-compose.yml -f observability.yml config` → exit 0.
- `docker compose -f docker-compose.yml -f docker-compose.test.yml config` →
  exit 0; `config --services` lists infra only.
- `promtool check config infrastructure/prometheus/prometheus.yml` → **SUCCESS**.
- `otelcol validate --config infrastructure/otel-collector/config.yaml` (inside
  `otel/opentelemetry-collector:0.158.0`) → exit 0.
- Grafana provisioning YAML parses.
- **Live smoke test**: full stack + overlay up; a smoke script configured the
  facade with `exporter_name="otlp-http"`, `endpoint="http://localhost:4318"`
  and emitted nested `tracer.span` calls. Collector debug output:
  `"resource spans": 1, "spans": 2`. This is what exposed the missing
  `/v1/traces` path.
- Smoke containers torn down afterward; only the four infra containers remain up.
- `ruff check` on changed Python files: **clean**. `mypy` (scoped):
  **clean — 18 source files**. `tests/test_observability.py`: **27 passed**.

## What I Learned

- `OTLPSpanExporter` appends `/v1/traces` **only** to its env-var default path;
  an explicit `endpoint=` is used verbatim. Any config that passes a bare
  host:port silently 404s and drops every span — the collector logs nothing,
  so this fails invisible. The facade must own path normalization.
- Compose `profiles` are the cleanest way to make "bring up only infra for the
  test suite" a structural guarantee rather than an operator habit.
- Validate configs against the real binaries (`promtool`, `otelcol validate`)
  before merging — they catch schema drift that YAML parsing never will.

## Remaining Technical Debt

- The collector exports to `debug`; forwarding to Tempo/Jaeger is the documented
  config swap, not yet exercised (no backend chosen).
- No Grafana dashboards are provisioned yet — datasource only. Dashboards are a
  follow-up, not part of 4B.
- Full-suite flake `test_due_retry_is_republished_and_requeued` is pre-existing
  DB-state flakiness (retry tests leave `RETRYING` jobs that become due on later
  runs) and unrelated to Phase 4 — this phase changed no runtime worker logic.
- Phase 5 (ADR-010, CHANGELOG, architecture docs, `.env.example`, tag) is next.

## Ready for Phase 5?

**Yes.** The overlay boots the full stack onto real tracing + metrics, the
infra-only test override is validated, all configs pass against the real tools,
the deploy smoke test proved an actual OTLP span reaches the collector (and
caught a real silent-drop bug now fixed and tested), and the core stack still
runs without the overlay. Phase 5 (docs + `.env.example` + tag) can proceed.

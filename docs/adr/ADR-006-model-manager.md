# ADR-006: ModelManager lifecycle — load the model once, share across jobs

- **Status:** Accepted
- **Date:** 2026-08-05
- **Deciders:** Architecture review
- **Related:** [system-architecture.md](../architecture/system-architecture.md), [ADR-002-rabbitmq.md](ADR-002-rabbitmq.md)

## Context

The legacy `inference_engine.py` loaded the Keras model lazily in a module-global
(`_load_model()`), once per process, on first request. Loading the N2N U-Net
takes 30–60s and allocates hundreds of MB. Sprint 3 moves inference into the
worker process, which must process many jobs per lifetime. Reloading the model
per job would make every scan pay the load cost and risk OOM under queue bursts.

## Decision

Introduce a `ModelManager` class in `worker/model_manager.py` owned by the
worker process:

- `startup()` — load TensorFlow, load weights once, detect GPU (best-effort),
  capture the git commit of the loaded weights, and persist a
  `model_versions` row (or reuse the existing one).
- `get_pipeline()` — return the cached pipeline (blocking-load once, then
  no-op). This is the seam the orchestrator calls for inference.
- `shutdown()` — release the model on worker shutdown.

The worker constructs one `ModelManager` at startup and never reconstructs it
per job. CPU is the default; GPU detection is best-effort metadata only.

## Rationale

- Keeps the proven "load once" property of the legacy engine while making the
  lifecycle explicit and testable.
- Decouples weight metadata persistence (`model_versions`) from the inference
  call path.
- A single seam (`get_pipeline`) keeps the orchestrator model-agnostic.

## Alternatives considered

- **Module-global lazy singleton (legacy pattern)** — implicit, hard to reset
  in tests, no startup hook for warm-up or metadata.
- **Reload per job** — rejected: load cost dominates scan latency and risks
  memory pressure.
- **Dependency-injected into every call** — no shared lifecycle holder; the
  worker still needs one owner.

## Consequences

**Positive**
- One load per worker process; subsequent jobs pay only inference time.
- Model/weights provenance (`git_commit`, `gpu_name`, `params_json`) recorded
  once per `model_versions` row.

**Negative**
- Worker startup latency increases (model load) — acceptable, done once.
- Memory held for process lifetime; `shutdown()` must be explicit.

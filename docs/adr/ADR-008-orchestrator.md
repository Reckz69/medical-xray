# ADR-008: Worker orchestration — `worker/orchestrator.py` owns the pipeline flow

- **Status:** Accepted
- **Date:** 2026-08-05
- **Deciders:** Architecture review
- **Related:** [ADR-006-model-manager.md](ADR-006-model-manager.md), [ADR-007-common-image.md](ADR-007-common-image.md)

## Context

Sprint 2B left `worker/pipeline.py` as an identity seam returning a single
processed byte blob; the executor uploaded one `ENHANCED` output. Sprint 3
replaces the identity with the real denoising pipeline that produces four
outputs (`ORIGINAL`, `NOISE_MAP`, `UNET`, `ENHANCED`), a routing decision,
measured noise variance, and per-stage timing. The executor must stay a
persistence/transport concern while a dedicated coordinator runs the ML flow.

## Decision

Rename the seam to `worker/orchestrator.py` and expose:

```python
async def run(data: bytes, *, fmt: str, model_manager: ModelManager) -> PipelineResult:
```

`PipelineResult` carries the four encoded outputs, `routing_message`,
`noise_variance`, `was_bypassed`, and per-stage timings
(`download/conversion/preprocessing/inference/postprocessing/encode/total`).
The orchestrator coordinates, in order:

1. conversion (CommonImage) → 2. preprocessing (tiling, normalization, Canny
   noise variance) → 3. routing (bypass or AI) → 4. inference (tiled threaded
   `predict`) → 5. postprocessing (CLAHE + unsharp mask) → 6. encode outputs.

The executor calls `orchestrator.run`, uploads each output object, persists
`ScanOutput` rows for all four types, records `model_id`, `noise_variance`, and
`processing_time_ms`, and only then publishes the lifecycle event. Naming it
`orchestrator` (not `pipeline`) reflects that it coordinates the staged modules
rather than containing the pipeline itself.

## Rationale

- Executor stays transport/persistence-only; orchestrator owns the ML flow and
  its timing — the seam `test_worker.py` can patch.
- Per-stage timings originate in exactly one place (the orchestrator).
- Matches the legacy `run_pipeline` contract (`DenoiseResult`) so the port is a
  faithful translation.

## Alternatives considered

- **Keep `worker/pipeline.py`** — the name implies the whole pipeline lives
  there, but the flow is now orchestration across `converters`, `preprocess`,
  `inference`, `postprocess`.
- **Fold everything into the executor** — couples persistence with inference;
  hard to patch, harder to time per stage.
- **Multiple seam calls from executor** — pushes stage knowledge into the
  executor and spreads timing logic.

## Consequences

**Positive**
- Clean patch seam for `test_worker.py`; stage timings centralized; executor
  unchanged in shape from Sprint 2B.
- Four outputs persisted with no API/schema/queue changes.

**Negative**
- A rename that touches the executor import; must keep `orchestrator.run`
  signature stable across Sprint 3.

# AI Engineering Guide

Rules for AI-assisted development on this repository. Enforced by the
maintainer and by the Definition of Done. The goal: every merge is explainable,
reviewable, and evidence-driven — not a black box of generated code.

## Definition of Done (DoD)

A change is done only when **all** of these hold:

- [ ] Implementation is complete for the requested scope.
- [ ] Unit tests pass.
- [ ] Integration tests pass.
- [ ] `ruff check` passes (no new errors).
- [ ] `mypy` passes on the changed modules.
- [ ] `docker compose -f deploy/docker-compose.yml config` is valid (if infra
      changed).
- [ ] Docs are updated (architecture/sequence diagrams where relevant).
- [ ] `docs/CHANGELOG.md` is updated.
- [ ] OpenAPI reflects any API change (no silent contract drift).
- [ ] One logical commit (or a small, reviewable series).
- [ ] Tagged if it completes a sprint milestone (`sprint-N`, `sprint-N.M`).

## Never

- Never delete or rewrite the frozen legacy modules
  (`backend/inference_engine.py`, `backend/main.py`, `backend/test_api.py`).
  They are the reference oracle until the decommissioning sprint. The `# LEGACY
  - FROZEN` header stays on them.
- Never change the API contract, auth, storage layer, queue topology, or DB
  schema without an ADR and an explicit decision.
- Never run the worker while integration tests execute (shared dev queue).
- Never commit secrets or model weights (`.keras` is gitignored).
- Never make architectural changes without evidence: a failing test, a
  production bug, a measurable performance bottleneck, or a new requirement.
- Never add the `data:` prefix to worker-encoded PNGs unless a consumer needs a
  data URI (the worker persists raw bytes; data URIs are a legacy API concern).
- Never let business code import Prometheus / OpenTelemetry / observability
  infrastructure directly. Everything observable goes through the single
  facade in `gateway/core/observability/` (ADR-010), and every facade component
  has a disabled-mode no-op contract — no `if enabled` branching at call sites.
- Never add a dependency without a written justification in the review doc:
  what problem it solves, why existing code cannot solve it, and its cost
  (footprint, upgrade surface, security).

## Always

- Start from the legacy oracle: when porting a stage, first run the legacy
  function on the same input and record its output as the expected result.
- Explain every new module/class/public function without looking at the code:
  - Why is this responsible for this task?
  - Why is it in this folder/package?
  - Why was this abstraction chosen (vs. the alternatives)?
  - What alternatives were considered and rejected?
  - What would break if this were removed?
  If you cannot answer these, spend 15–20 minutes reviewing before moving on.
- Keep stages incremental: one commit per stage (3.1 → 3.6), each green and
  gated, before the next.
- Record per-stage timing from day one and persist the total to
  `scan.processing_time_ms`.
- Add/update an ADR for every significant decision (see `docs/adr/`).
- Implement one abstraction per review gate. When a gate spans several
  observability abstractions (logging, metrics, tracing), land and review them
  one at a time — never multiple facades in a single un-reviewed commit.
- Write a per-phase review to `docs/reviews/sprint-<n>-phase<m>-review.md`
  (template: Goal / Files Changed / Architecture Decisions / Tests Added /
  Ruff / MyPy / Performance Impact / What I Learned / Remaining Technical
  Debt / Ready for the next phase?) and explain-before-merge every file:
  why it exists, why here, why not elsewhere, what problem it solves, what
  alternatives were considered, its blast radius, and which tests protect it.
  If you cannot answer those, review before moving on.
- Keep every merge deployable: the app stack must never depend on optional
  observability infrastructure (Grafana/Jaeger/Collector). Those live in a
  separate overlay so the core stack runs without them.

## Review gates (Sprint 3)

After **every** stage, the next commit is not made until the gate passes:

- **3.1** CommonImage works; PNG/JPEG/DICOM tests pass.
- **3.2** Preprocessing matches legacy output; tiling verified.
- **3.3** Model loads once; memory stable; worker startup verified.
- **3.4** Inference output matches legacy implementation.
- **3.5** Enhanced image quality validated; golden-image tests pass
  (`psnr > 35` AND `ssim > 0.95`, scikit-image, `@pytest.mark.golden`).
- **3.6** End-to-end workflow: upload → queue → worker → outputs stored →
  metadata updated → job completed. Only then tag `sprint-3`.

## Golden tests

Golden tests assert regression gates, not benchmarks:

```python
@pytest.mark.golden
def test_enhanced_quality() -> None:
    assert psnr(enhanced, legacy) > 35
    assert ssim(enhanced, legacy) > 0.95
```

They live under `tests/golden/` and are excluded from the default suite
(marker `golden`).

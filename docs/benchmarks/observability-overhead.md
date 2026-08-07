# Observability overhead — tracing OFF vs ON

- Date: 2026-08-07 13:18 UTC
- Git commit: `b8effff`
- Rounds per mode: 6 (median taken, last pair order-swapped)
- Jobs per round: 200
- Tracing ON uses `SimpleSpanProcessor` + `InMemorySpanExporter` (sync, conservative upper bound; production uses `BatchSpanProcessor`)

## Environment

- Host: Narendra-ka-MacBook-Air.local (arm64)
- CPU: Apple M2
- Logical cores: arm / 8
- Python: 3.11.15

## Part A — per-seam micro cost (median ns)

| seam | OFF | ON | delta |
|---|---|---|---|
| `tracer.span` | 917 ns | 19125 ns | +18208 ns |
| `tracer.span_from_traceparent` | 833 ns | 28209 ns | +27376 ns |
| `build_message_headers` | 333 ns | 1125 ns | +792 ns |

## Part B — simulated worker job (7 spans + header build, ~1 ms CPU work)

- OFF: **193.6 jobs/s**
- ON: **192.5 jobs/s**
- Overhead: **+0.55%**

## Gate result

- Threshold: tracing ON overhead < 5% → **PASS** (+0.55%).
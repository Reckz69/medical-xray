"""Tracing overhead benchmark for Sprint 4B (performance gate).

Measures the cost of OpenTelemetry tracing at the exact seams introduced in
Phase 3, tracing OFF vs ON:

* ``tracer.span`` / ``tracer.span_from_traceparent`` context managers
  (gateway middleware, worker consumer, orchestrator pipeline stages),
* ``queue.build_message_headers`` W3C ``traceparent`` injection (publish).

Two measurements:

* Part A — seam micro-cost: median wall time per span lifecycle and per header
  build, OFF vs ON, in nanoseconds.
* Part B — simulated worker job: 7 spans (1 consumer continuation + 1 job + 5
  pipeline stages) plus one header build around ~1 ms of CPU work per job.
  Reports jobs/s OFF vs ON and the overhead percentage.

``tracer.configure(enabled=True, exporter=...)`` is exercised with a
synchronous ``InMemorySpanExporter`` via ``SimpleSpanProcessor``. Production
uses ``BatchSpanProcessor`` (export on a background thread), which is strictly
cheaper on the hot path, so this is a conservative upper bound. The gate is
overhead < 5%.

Writes a markdown report to ``docs/benchmarks/observability-overhead.md``.

Usage (from ``backend/``):

    .venv/bin/python scripts/benchmark_observability.py [--rounds 5] [--jobs 200] [--out ../docs/benchmarks/observability-overhead.md]
"""

from __future__ import annotations

import argparse
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from gateway.core.observability import tracer
from gateway.core.queue import build_message_headers

_DEFAULT_OUT = _REPO_ROOT / "docs" / "benchmarks" / "observability-overhead.md"
_TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

_PIPELINE_STAGES = (
    "pipeline.convert",
    "pipeline.preprocess",
    "pipeline.inference",
    "pipeline.postprocess",
    "pipeline.encode",
)


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=_REPO_ROOT,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001 — provenance is best-effort
        return "unknown"


def _machine_info() -> list[str]:
    brand = "unknown"
    try:
        if platform.system() == "Darwin":
            out = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                check=True,
            )
            brand = out.stdout.strip()
        else:
            with open("/proc/cpuinfo", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("model name"):
                        brand = line.split(":", 1)[1].strip()
                        break
    except Exception:  # noqa: BLE001, S110 — metadata is best-effort
        pass
    return [
        f"- Host: {platform.node()} ({platform.machine()})",
        f"- CPU: {brand}",
        f"- Logical cores: {platform.processor()} / {__import__('os').cpu_count()}",
        f"- Python: {platform.python_version()}",
    ]


class BusyWork:
    """Fixed-size CPU workload, calibrated to ~1 ms on this machine."""

    def __init__(self, target_ms: float = 1.0) -> None:
        self._iterations = self._calibrate(target_ms)

    @staticmethod
    def _spin(iterations: int) -> int:
        acc = 0
        for i in range(iterations):
            acc += i * i
        return acc

    def _calibrate(self, target_ms: float) -> int:
        probe = 200_000
        start = time.perf_counter()
        self._spin(probe)
        per_iter = (time.perf_counter() - start) / probe
        if per_iter <= 0:
            return probe
        return max(1, int(target_ms * 1e-3 / per_iter))

    def run(self) -> None:
        self._spin(self._iterations)


def _measure_seam(rounds: int) -> dict[str, float]:
    """Part A: per-seam wall cost in nanoseconds, median over ``rounds`` samples."""
    off: dict[str, list[float]] = {k: [] for k in ("span", "span_from_traceparent", "headers")}
    on: dict[str, list[float]] = {k: [] for k in ("span", "span_from_traceparent", "headers")}

    tracer.configure(enabled=False)
    for _ in range(rounds):
        start = time.perf_counter()
        with tracer.span("sample"):
            pass
        off["span"].append((time.perf_counter() - start) * 1e9)

        start = time.perf_counter()
        with tracer.span_from_traceparent(_TRACEPARENT, "sample"):
            pass
        off["span_from_traceparent"].append((time.perf_counter() - start) * 1e9)

        start = time.perf_counter()
        build_message_headers("t" * 32, "c" * 32)
        off["headers"].append((time.perf_counter() - start) * 1e9)

    exporter = InMemorySpanExporter()
    tracer.configure(enabled=True, service="benchmark", exporter=exporter)
    for _ in range(rounds):
        start = time.perf_counter()
        with tracer.span("sample"):
            pass
        on["span"].append((time.perf_counter() - start) * 1e9)

        start = time.perf_counter()
        with tracer.span_from_traceparent(_TRACEPARENT, "sample"):
            pass
        on["span_from_traceparent"].append((time.perf_counter() - start) * 1e9)

        start = time.perf_counter()
        build_message_headers("t" * 32, "c" * 32)
        on["headers"].append((time.perf_counter() - start) * 1e9)
    tracer.configure(enabled=False)

    return {
        "span_off": statistics.median(off["span"]),
        "span_on": statistics.median(on["span"]),
        "cont_off": statistics.median(off["span_from_traceparent"]),
        "cont_on": statistics.median(on["span_from_traceparent"]),
        "headers_off": statistics.median(off["headers"]),
        "headers_on": statistics.median(on["headers"]),
    }


def _simulate_job(work: BusyWork, publish: bool = True) -> None:
    """One worker job: consumer continuation + job span + 5 pipeline spans.

    Mirrors ``worker.main`` -> ``executor.process_message`` ->
    ``orchestrator.run`` plus the publish seam.
    """
    with tracer.span_from_traceparent(_TRACEPARENT, "worker.inference.run"):
        with tracer.span("worker.process_job"):
            for stage in _PIPELINE_STAGES:
                with tracer.span(stage):
                    work.run()
        if publish:
            build_message_headers("t" * 32, "c" * 32)


def _measure_jobs(rounds: int, jobs: int) -> dict[str, float]:
    """Part B: median jobs/s for each mode."""
    work = BusyWork()
    results: dict[str, list[float]] = {"off": [], "on": []}

    def _round(enabled: bool) -> float:
        exporter: InMemorySpanExporter | None = None
        if enabled:
            exporter = InMemorySpanExporter()
            tracer.configure(enabled=True, service="benchmark", exporter=exporter)
        else:
            tracer.configure(enabled=False)
        _simulate_job(work)  # warmup
        start = time.perf_counter()
        for _ in range(jobs):
            _simulate_job(work)
        elapsed = time.perf_counter() - start
        if enabled and exporter is not None:
            expected = jobs * (1 + 1 + len(_PIPELINE_STAGES))
            if len(exporter.get_finished_spans()) < expected:
                raise RuntimeError("tracing ON did not record expected spans")
        tracer.configure(enabled=False)
        return jobs / elapsed

    for _ in range(rounds):
        results["off"].append(_round(False))
        results["on"].append(_round(True))
    # alternate order for the last round pair to cancel thermal drift
    results["on"].append(_round(True))
    results["off"].append(_round(False))

    return {
        "jobs_off": statistics.median(results["off"]),
        "jobs_on": statistics.median(results["on"]),
    }


def _render(rounds: int, jobs: int, seams: dict[str, float], jobs_stats: dict[str, float]) -> str:
    overhead = (jobs_stats["jobs_off"] - jobs_stats["jobs_on"]) / jobs_stats["jobs_off"] * 100
    lines = [
        "# Observability overhead — tracing OFF vs ON",
        "",
        f"- Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Git commit: `{_git_commit()}`",
        f"- Rounds per mode: {rounds + 1} (median taken, last pair order-swapped)",
        f"- Jobs per round: {jobs}",
        "- Tracing ON uses `SimpleSpanProcessor` + `InMemorySpanExporter` (sync, conservative upper bound; production uses `BatchSpanProcessor`)",
        "",
        "## Environment",
        "",
        *_machine_info(),
        "",
        "## Part A — per-seam micro cost (median ns)",
        "",
        "| seam | OFF | ON | delta |",
        "|---|---|---|---|",
        f"| `tracer.span` | {seams['span_off']:.0f} ns | {seams['span_on']:.0f} ns | {seams['span_on'] - seams['span_off']:+.0f} ns |",
        f"| `tracer.span_from_traceparent` | {seams['cont_off']:.0f} ns | {seams['cont_on']:.0f} ns | {seams['cont_on'] - seams['cont_off']:+.0f} ns |",
        f"| `build_message_headers` | {seams['headers_off']:.0f} ns | {seams['headers_on']:.0f} ns | {seams['headers_on'] - seams['headers_off']:+.0f} ns |",
        "",
        "## Part B — simulated worker job (7 spans + header build, ~1 ms CPU work)",
        "",
        f"- OFF: **{jobs_stats['jobs_off']:.1f} jobs/s**",
        f"- ON: **{jobs_stats['jobs_on']:.1f} jobs/s**",
        f"- Overhead: **{overhead:+.2f}%**",
        "",
        "## Gate result",
        "",
        (
            f"- Threshold: tracing ON overhead < 5% → **{'PASS' if overhead < 5 else 'FAIL'}**"
            f" ({overhead:+.2f}%)."
        ),
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tracing overhead benchmark (Sprint 4B gate)")
    parser.add_argument("--rounds", type=int, default=5, help="timed rounds per mode")
    parser.add_argument("--jobs", type=int, default=200, help="jobs per round")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT, help="markdown report path")
    args = parser.parse_args()

    seams = _measure_seam(args.rounds)
    jobs_stats = _measure_jobs(args.rounds, args.jobs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_render(args.rounds, args.jobs, seams, jobs_stats), encoding="utf-8")
    print(args.out.read_text())


if __name__ == "__main__":
    main()

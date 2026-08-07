"""CPU baseline benchmark for the denoising pipeline (Sprint 3.5).

Loads the real model once, runs ``worker.orchestrator.run`` over a set of
representative X-ray fixtures (one warmup + ``--repeats`` timed runs each),
and records per-stage timings (conversion / preprocessing / inference /
postprocessing / encode / total) from the existing ``StageTimings`` record.
Writes a markdown report to ``docs/benchmarks/cpu-baseline.md``.

Usage (from ``backend/``):

    .venv/bin/python scripts/benchmark_cpu.py [--repeats 3] [--out ../docs/benchmarks/cpu-baseline.md]
"""

from __future__ import annotations

import argparse
import asyncio
import platform
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from worker.model_manager import ModelManager
from worker.orchestrator import StageTimings, run

_DEFAULT_IMAGES = [
    "dataset_x-ray1.png",
    "foot_friend_x-ray.jpeg",
    "low_nosie_dicom.dicom",
    "high_noise_dicom.dicom",
]
_DEFAULT_OUT = _REPO_ROOT / "docs" / "benchmarks" / "cpu-baseline.md"
_STAGES = ("conversion_ms", "preprocessing_ms", "inference_ms", "postprocessing_ms", "encode_ms", "total_ms")


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


@dataclass
class RunStats:
    label: str
    runs: list[StageTimings]
    was_bypassed: bool
    noise_variance: float
    width: int
    height: int

    def summarize(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for stage in _STAGES:
            values = sorted(getattr(r, stage) for r in self.runs)
            out[stage] = values[0]
            if len(values) < 2:
                out[f"{stage}_p50"] = values[0]
                out[f"{stage}_p95"] = values[0]
            else:
                out[f"{stage}_p50"] = statistics.median(values)
                out[f"{stage}_p95"] = statistics.quantiles(values, n=20)[18]
            out[f"{stage}_max"] = values[-1]
        return out


def _machine_info() -> list[str]:
    return [
        f"- Host: {platform.node()} ({platform.machine()})",
        f"- CPU: {_cpu_brand()}",
        f"- Logical cores: {_os_cpu_count()}",
    ]


def _cpu_brand() -> str:
    try:
        if platform.system() == "Darwin":
            out = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                check=True,
            )
            return out.stdout.strip()
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:  # noqa: BLE001 — metadata is best-effort
        return "unknown"
    return "unknown"


def _os_cpu_count() -> int | None:
    import os

    return os.cpu_count()


def _py_env() -> list[str]:
    lines = [
        f"- Python: {platform.python_version()}",
    ]
    try:
        import tensorflow as tf

        lines.append(f"- TensorFlow: {tf.__version__}")
    except Exception:  # noqa: BLE001 — metadata is best-effort
        lines.append("- TensorFlow: unknown")
    return lines


async def _run_once(data: bytes, name: str, manager: ModelManager) -> tuple[StageTimings, bool, float, int, int]:
    result = await run(
        data,
        fmt="x",
        model_manager=manager,
        original_name=name,
    )
    return result.timings, result.was_bypassed, result.noise_variance, result.width, result.height


def _format_ms(value: float) -> str:
    return f"{value:,.1f}"


def _render(stats: list[RunStats]) -> str:
    commit = _git_commit()
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    headers = ["metric"] + [s.label for s in stats]
    lines = [
        "# CPU baseline — denoising pipeline",
        "",
        f"- Date: {now}",
        f"- Git commit: `{commit}`",
        "- Weights: `n2n_unet_best_weights04 (2).keras`",
        f"- Runs per image: {len(stats[0].runs) if stats else 0} timed (+ 1 warmup)",
        "",
        "## Environment",
        "",
        *_machine_info(),
        *_py_env(),
        "",
        "## Per-image results (ms)",
        "",
        "| metric | " + " | ".join(headers) + " |",
        "|" + "---|" * len(headers),
    ]
    for stage in _STAGES:
        row = [stage]
        for s in stats:
            summ = s.summarize()
            row.append(f"{_format_ms(summ[stage])} (p50 {_format_ms(summ[f'{stage}_p50'])})")
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "## Routing per image", "", "| image | width x height | routing | noise_variance |", "|---|---|---|---|"]
    for s in stats:
        route = "PATH A (AI engaged)" if not s.was_bypassed else "PATH B (bypassed)"
        lines.append(f"| {s.label} | {s.width}x{s.height} | {route} | {s.noise_variance:.1f} |")
    return "\n".join(lines)


async def _benchmark(images: list[str], repeats: int, out: Path) -> None:
    manager = ModelManager()
    start = time.perf_counter()
    manager.startup()
    load_ms = (time.perf_counter() - start) * 1000
    print(f"model load: {load_ms:.0f}ms")

    root = _REPO_ROOT / "Images"
    stats: list[RunStats] = []
    for name in images:
        data = (root / name).read_bytes()
        await _run_once(data, name, manager)
        print(f"warmup done: {name}")
        runs: list[StageTimings] = []
        was_bypassed = False
        noise_variance = 0.0
        width = height = 0
        for i in range(repeats):
            timing, was_bypassed, noise_variance, width, height = await _run_once(data, name, manager)
            runs.append(timing)
            print(f"  [{i + 1}/{repeats}] {name}: total {timing.total_ms:.1f}ms")
        stats.append(
            RunStats(
                label=name,
                runs=runs,
                was_bypassed=was_bypassed,
                noise_variance=noise_variance,
                width=width,
                height=height,
            )
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render(stats), encoding="utf-8")
    print(f"report written: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="CPU baseline benchmark for the denoising pipeline")
    parser.add_argument("--repeats", type=int, default=3, help="timed runs per image")
    parser.add_argument("--images", nargs="*", default=_DEFAULT_IMAGES, help="image names under ../Images/")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT, help="markdown report path")
    args = parser.parse_args()
    asyncio.run(_benchmark(args.images, args.repeats, args.out))


if __name__ == "__main__":
    main()

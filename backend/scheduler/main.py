"""Scheduler entrypoint — periodic retry + cleanup loops (ADR-009).

Run via ``python -m scheduler.main`` or the Docker scheduler service.

* Retry pass (republish due retries, recover stalled RUNNING jobs) runs every
  ``scheduler_poll_interval_seconds``.
* Cleanup runs every ``scheduler_cleanup_interval_seconds`` via the internal
  timer (production default) and on demand via the ``cleanup.run`` command
  consumer. Both triggers share ``CleanupService.run_cleanup`` (distributed
  lock, metrics, idempotent), so a future CronJob / EventBridge can drive
  cleanup without changing the cleanup logic.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from datetime import UTC, datetime

import aio_pika
from aio_pika import ExchangeType

from gateway.core.config import settings
from gateway.core.db import SessionLocal
from gateway.core.observability import init_observability, log_context
from gateway.core.queue import CMD_CLEANUP_RUN, COMMANDS_EXCHANGE, queue
from gateway.core.redis import redis
from scheduler import retry_jobs
from scheduler.cleanup import CleanupService
from scheduler.consumer import handle_cleanup_run
from scheduler.metrics import metrics

logger = logging.getLogger("denoise.scheduler")

CLEANUP_QUEUE = "scheduler.cleanup"
HEARTBEAT_FILE = "/tmp/scheduler.heartbeat"


def _touch_heartbeat() -> None:
    """Stamp the liveness file consumed by the container healthcheck."""
    try:
        with open(HEARTBEAT_FILE, "w", encoding="utf-8") as fh:
            fh.write(datetime.now(UTC).isoformat())
    except OSError:
        pass


async def run_once() -> dict:
    """One retry cycle (republish + stall recovery + unconfirmed)."""
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        report = await retry_jobs.run_once(session, now=now)
        await session.commit()
    metrics.cycles += 1
    metrics.last_run_at = now
    logger.info("scheduler cycle: %s", report)
    return report


async def _consume_cleanup_commands(cleanup_service: CleanupService) -> None:
    """Consume `cleanup.run` commands; each triggers the shared cleanup pass."""
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    commands = await channel.declare_exchange(
        COMMANDS_EXCHANGE, ExchangeType.TOPIC, durable=True
    )
    cleanup_queue = await channel.declare_queue(CLEANUP_QUEUE, durable=True)
    await cleanup_queue.bind(commands, CMD_CLEANUP_RUN)

    async def on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
        async with message.process(requeue=True):
            payload = json.loads(message.body)
            logger.info("received cleanup.run command; running cleanup")
            await handle_cleanup_run(payload, service=cleanup_service)

    await cleanup_queue.consume(on_message, no_ack=False)
    logger.info(
        "scheduler consuming %s from %s (queue=%s)",
        CMD_CLEANUP_RUN,
        COMMANDS_EXCHANGE,
        CLEANUP_QUEUE,
    )
    try:
        await asyncio.Event().wait()
    finally:
        await connection.close()


async def main() -> None:
    init_observability(
        service="scheduler",
        log_level="DEBUG" if settings.debug else "INFO",
        otel_enabled=settings.otel_enabled,
    )
    logger.info(
        "scheduler starting: poll=%ds cleanup=%ds stall=%ds lock_ttl=%ds",
        settings.scheduler_poll_interval_seconds,
        settings.scheduler_cleanup_interval_seconds,
        settings.job_stall_timeout_seconds,
        settings.scheduler_cleanup_lock_ttl_seconds,
    )

    cleanup_service = CleanupService()
    consumer_task = asyncio.create_task(_consume_cleanup_commands(cleanup_service))

    last_cleanup = 0.0
    try:
        while True:
            cycle_started = time.monotonic()
            # One trace id per cycle so all of a cycle's log lines correlate.
            cycle_trace_id = uuid.uuid4().hex
            with log_context(trace_id=cycle_trace_id):
                try:
                    await run_once()
                except Exception as exc:
                    logger.exception("scheduler cycle failed")
                    metrics.last_error = str(exc)

                if (
                    time.monotonic() - last_cleanup
                    >= settings.scheduler_cleanup_interval_seconds
                ):
                    report = await cleanup_service.run_cleanup(source="timer")
                    last_cleanup = time.monotonic()
                    logger.info("scheduler cleanup (timer): %s", report)

            _touch_heartbeat()
            elapsed = time.monotonic() - cycle_started
            await asyncio.sleep(
                max(settings.scheduler_poll_interval_seconds - elapsed, 1)
            )
    finally:
        consumer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consumer_task
        await queue.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())

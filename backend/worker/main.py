"""Worker entrypoint.

Consumes `inference.run` commands from the `commands` exchange and executes
them, then publishes `scan.completed` / `scan.failed` events to the `events`
exchange. Run via ``python -m worker.main`` or the Docker worker service.

The ModelManager is constructed once and started (blocking model load) in a
worker thread before consumption begins, so every job shares the loaded model
(ADR-006).
"""

from __future__ import annotations

import asyncio
import json
import logging

import aio_pika
from aio_pika import ExchangeType

from gateway.core.config import settings
from gateway.core.logging import configure_logging
from gateway.core.queue import CMD_INFERENCE_RUN, COMMANDS_EXCHANGE
from worker import executor
from worker.consumer import handle_inference_run

logger = logging.getLogger("denoise.worker")


async def _on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    async with message.process(requeue=True):
        payload = json.loads(message.body)
        headers = message.headers or {}
        logger.info(
            "consumed %s for scan %s job %s",
            CMD_INFERENCE_RUN,
            payload.get("scan_id"),
            payload.get("job_id"),
        )
        await handle_inference_run(
            payload,
            trace_id=headers.get("trace_id", ""),
            correlation_id=headers.get("correlation_id", ""),
        )


async def main() -> None:
    configure_logging("DEBUG" if settings.debug else "INFO")
    await asyncio.to_thread(executor.model_manager.startup)
    logger.info(
        "model %s (%s) ready [gpu=%s]",
        executor.model_manager.model_name,
        executor.model_manager.model_version,
        executor.model_manager.gpu_name or "cpu",
    )

    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    commands = await channel.declare_exchange(
        COMMANDS_EXCHANGE, ExchangeType.TOPIC, durable=True
    )
    queue = await channel.declare_queue("inference.worker", durable=True)
    await queue.bind(commands, CMD_INFERENCE_RUN)
    await queue.consume(_on_message, no_ack=False)
    logger.info("worker consuming %s from %s", CMD_INFERENCE_RUN, COMMANDS_EXCHANGE)
    try:
        await asyncio.Event().wait()
    finally:
        await connection.close()
        executor.model_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())

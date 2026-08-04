"""Worker entrypoint.

Consumes `inference.run` commands from the `commands` exchange and executes
them, then publishes `scan.completed` / `scan.failed` events to the `events`
exchange. Run via ``python -m worker.main`` or the Docker worker service.
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


if __name__ == "__main__":
    asyncio.run(main())

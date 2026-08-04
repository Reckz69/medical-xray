"""RabbitMQ command/event publishing (ADR-002).

Two durable topic exchanges:

    commands        events
    ├── inference.run       ├── scan.completed
    ├── cleanup.run         ├── scan.failed
    └── notification.send   └── user.created
                            └── report.generated

The gateway publishes `commands`; the worker consumes commands and publishes
`events`; future subscribers consume events. `trace_id` and `correlation_id`
ride in the AMQP headers so a job can be correlated end-to-end
(API -> RabbitMQ -> worker -> S3 -> DB).

The client connects lazily (first publish) and tolerates broker restarts via
a robust connection.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import aio_pika
from aio_pika import DeliveryMode, ExchangeType
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractRobustConnection

from gateway.core.config import settings

COMMANDS_EXCHANGE = "commands"
EVENTS_EXCHANGE = "events"

# Commands (gateway -> worker)
CMD_INFERENCE_RUN = "inference.run"
CMD_CLEANUP_RUN = "cleanup.run"
CMD_NOTIFICATION_SEND = "notification.send"

# Events (worker / domains -> subscribers)
EVT_SCAN_COMPLETED = "scan.completed"
EVT_SCAN_FAILED = "scan.failed"
EVT_USER_CREATED = "user.created"
EVT_REPORT_GENERATED = "report.generated"


def new_correlation_id() -> str:
    return uuid.uuid4().hex


class QueueClient:
    def __init__(self, url: str | None = None) -> None:
        self._url = url or settings.rabbitmq_url
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._commands: AbstractExchange | None = None
        self._events: AbstractExchange | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        async with self._lock:
            if self._connection is not None and not self._connection.is_closed:
                return
            self._connection = await aio_pika.connect_robust(self._url)
            self._channel = await self._connection.channel()
            self._commands = await self._channel.declare_exchange(
                COMMANDS_EXCHANGE, ExchangeType.TOPIC, durable=True
            )
            self._events = await self._channel.declare_exchange(
                EVENTS_EXCHANGE, ExchangeType.TOPIC, durable=True
            )

    async def close(self) -> None:
        async with self._lock:
            if self._connection is not None and not self._connection.is_closed:
                await self._connection.close()
            self._connection = None
            self._channel = None
            self._commands = None
            self._events = None

    async def publish_command(
        self,
        routing_key: str,
        payload: dict[str, Any],
        trace_id: str = "",
        correlation_id: str | None = None,
    ) -> None:
        await self._publish(COMMANDS_EXCHANGE, routing_key, payload, trace_id, correlation_id)

    async def publish_event(
        self,
        routing_key: str,
        payload: dict[str, Any],
        trace_id: str = "",
        correlation_id: str | None = None,
    ) -> None:
        await self._publish(EVENTS_EXCHANGE, routing_key, payload, trace_id, correlation_id)

    async def _publish(
        self,
        exchange_name: str,
        routing_key: str,
        payload: dict[str, Any],
        trace_id: str,
        correlation_id: str | None,
    ) -> None:
        if self._channel is None or self._commands is None or self._events is None:
            await self.connect()
        exchange = self._commands if exchange_name == COMMANDS_EXCHANGE else self._events
        assert self._channel is not None and exchange is not None
        message = aio_pika.Message(
            body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            headers={
                "trace_id": trace_id or "",
                "correlation_id": correlation_id or new_correlation_id(),
            },
        )
        await exchange.publish(message, routing_key)


queue = QueueClient()

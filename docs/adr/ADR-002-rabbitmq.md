# ADR-002: RabbitMQ for asynchronous job queue and events

- **Status:** Accepted
- **Date:** 2026-07-31
- **Deciders:** Architecture review
- **Related:** [system-architecture.md](../architecture/system-architecture.md), [sequence-inference.md](../architecture/sequence-inference.md)

## Context

Inference is heavy (Keras model, ~30–60s load, slow per-scan inference) and must
run outside the request path. The platform also needs future consumers
(notifications, analytics, billing, report generation) to react to domain events
without touching inference code.

## Decision

Use RabbitMQ with **two topic exchanges**:

```
commands        events
├── inference.run       ├── scan.completed
├── cleanup.run         ├── scan.failed
└── notification.send   └── user.created
                        └── report.generated
```

The API publishes `commands`; the worker consumes commands and publishes
`events`; future subscribers consume events.

## Rationale

- Broker-based decoupling: producer and consumer live/deploy independently
  (API process vs. worker process vs. future GPU pods).
- Durable queues, consumer acks, prefetch control (1 for GPU jobs), retry
  via dead-letter + `next_retry_at` scheduling.
- Two exchanges separate "do this" (commands, one consumer group) from "this
  happened" (events, many subscribers) — the core extensibility ask.
- W3C TraceContext propagates cleanly through AMQP message headers.
- Mature, self-hostable, Docker-friendly; K8s Operator support later.

## Alternatives considered

- **Redis pub/sub / streams** — no durable competing-consumer queues without
  extra work; Redis is explicitly not allowed to be authoritative here.
- **Polling from the API** — couples request path to job state; no events.
- **Celery** — AMQP broker underneath but bundles scheduling/execution opinion
  into one tool; we want a plain broker + dedicated worker.

## Consequences

**Positive**
- Async decoupling, reliable delivery, retries, event-driven future features.
- Worker process is independently deployable/scalable (future GPU pod).

**Negative**
- One more moving part (management UI, connection handling).
- Requires ack/timeout discipline and idempotent consumers.

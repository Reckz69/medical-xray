# Sequence — Inference (Worker)

Lifecycle: `RabbitMQ → Worker → MinIO → PostgreSQL → RabbitMQ (event)`.
PostgreSQL is the source of truth; the worker does **not** write Redis.

```mermaid
sequenceDiagram
    autonumber
    participant R as RabbitMQ
    participant W as Worker
    participant M as MinIO / S3
    participant P as PostgreSQL
    participant E as Events (RabbitMQ)

    R->>W: commands.inference.run {scan_id, job_id, trace_id}
    W->>P: UPDATE jobs → RUNNING (attempt++, worker_id, started_at)
    W->>M: download original object (decrypt via SSE server-side)
    M-->>W: bytes
    W->>W: converters: format → CommonImage
    Note over W: Pipeline: preprocess (tiling) →<br/>infer (U-Net) → postprocess (CLAHE+USM)

    alt pipeline succeeds
        W->>M: upload 4 outputs (ORIGINAL? no — noise_map, unet, enhanced)
        M-->>W: etags
        W->>P: INSERT scan_outputs rows + model_versions<br/>UPDATE scans (COMPLETED, metrics), jobs (COMPLETED)
        W->>E: publish events.scan.completed {scan_id, trace_id}
    else pipeline fails
        W->>P: UPDATE jobs → FAILED (error, attempt, next_retry_at) or RETRYING
        alt attempts exhausted
            W->>P: UPDATE scans → FAILED
            W->>E: publish events.scan.failed {scan_id, trace_id}
        end
    end
```

## Retry state machine

```
QUEUED ─▶ RUNNING ─▶ COMPLETED
              │
              ▼
           FAILED ─▶ RETRYING ─▶ RUNNING ─▶ ...  (attempt < max_attempts=3)
              │
              └── attempts exhausted ─▶ FAILED (terminal, error persisted)
```

- `RETRYING` jobs are picked up by `scheduler/retry_jobs.py` after
  `next_retry_at` backoff.
- A `CANCELLED` state exists for scans soft-deleted mid-flight.
- `job.trace_id` matches the originating request so a single upload is traceable
  across API → queue → worker → S3 → DB.

# Sequence — Scan Upload

Lifecycle: `Client → Gateway → MinIO → PostgreSQL → RabbitMQ`, returns `202` immediately.
Async inference happens later via the worker (see `sequence-inference.md`).

```mermaid
sequenceDiagram
    autonumber
    participant C as Client (Browser)
    participant G as Gateway (FastAPI)
    participant M as MinIO / S3
    participant P as PostgreSQL
    participant R as RabbitMQ

    C->>G: POST /api/v1/scans (multipart, Bearer JWT)
    Note over G: rate limit 20/h/user (Redis) · validate magic bytes<br/>PNG/JPEG/DICM header · decode · dims · 50MB max

    alt validation fails
        G-->>C: 422 { success:false, code:"VALIDATION_ERROR"|"SCAN_TOO_LARGE", trace_id }
    else valid
        G->>M: StorageProvider.upload(bucket, key, bytes)
        M-->>G: etag, checksum
        G->>P: INSERT objects, scans (QUEUED), scan_outputs, jobs (QUEUED)
        P-->>G: ids
        G->>R: publish commands.inference.run {scan_id, job_id, trace_id}
        G-->>C: 202 { success:true, data:{scan_id, status:"QUEUED"}, trace_id }
        Note over G: audit_logs: UPLOAD (user, ip, user_agent, trace_id)
    end
```

## Notes

- Upload is the only synchronous write path; everything after the RabbitMQ
  publish is async.
- The client never receives base64 images anymore — it polls
  `GET /api/v1/scans/{scan_id}` for status.
- The `original` output row (`scan_outputs.type = ORIGINAL`) points at the
  uploaded object.

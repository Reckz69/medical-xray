# Sequence — Download (Presigned URL)

Lifecycle: `Client → Gateway (verify + audit) → MinIO (direct download)`.
The browser downloads straight from object storage — FastAPI never proxies image bytes.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client (Browser)
    participant G as Gateway (FastAPI)
    participant P as PostgreSQL
    participant M as MinIO / S3

    C->>G: GET /api/v1/scans/{scan_id}/output/{type}/url (Bearer JWT)
    Note over G: rate limit 300/h/user (Redis)<br/>verify JWT + ownership (user/org)

    alt not owner or scan hidden
        G-->>C: 403 FORBIDDEN | 404 NOT_FOUND
    else authorized
        G->>P: read scan_outputs + objects (verify not deleted/archived)
        P-->>G: object metadata
        G->>P: INSERT audit_logs (action=DOWNLOAD, ip, user_agent, trace_id)
        G-->>C: 200 { success:true, data:{ url, expires_in:900, method:"GET" }, trace_id }
        C->>M: GET presigned URL
        M-->>C: image bytes (streamed by S3, SSE-decrypted at rest)
    end
```

## Rules

- Presigned URLs are short-lived (15 min default) and single-object scoped.
- Every download is audited (user, time, IP, device) — medical compliance requirement.
- No image data ever traverses the gateway: backend bandwidth is ~zero, CDN-friendly, cheaper at scale.
- Soft-deleted (`deleted_at` set) or archived (`lifecycle_state = ARCHIVED`) objects return `410`/`404`.

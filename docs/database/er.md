# PostgreSQL ER Diagram

> Status: Accepted — Phase 0 design artifact
> Conventions: every table has `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`.
> Every row that can be removed is soft-deleted via `deleted_at` / `deleted_by`
> (a `UUID` referencing `users.id`). Image bytes never live here — only metadata
> and object keys.

## Relationship diagram

```mermaid
erDiagram
    ORGANIZATIONS {
        uuid id PK "gen_random_uuid()"
        text name
        text plan "free | pro"
        bigint storage_limit_bytes
        timestamptz created_at
        timestamptz deleted_at "null = active"
        uuid deleted_by "FK users.id"
    }

    USERS {
        uuid id PK
        uuid organization_id FK
        citext email "UNIQUE"
        text name
        text role "patient | radiologist | admin"
        text status "active | suspended"
        timestamptz created_at
        timestamptz updated_at
        timestamptz last_login_at
        timestamptz deleted_at
        uuid deleted_by
    }

    CREDENTIALS {
        uuid user_id PK "FK users.id, 1:1"
        text password_hash "bcrypt"
        int refresh_token_version "bumped on rotate/logout"
        text mfa_secret "NULL for now"
        timestamptz updated_at
    }

    SCANS {
        uuid id PK
        uuid organization_id FK
        uuid user_id FK
        uuid model_id FK "model_versions.id, NULL before done"
        text status "QUEUED | RUNNING | COMPLETED | FAILED | CANCELLED"
        text original_name
        text format "PNG | JPEG | DICOM"
        bigint size_bytes
        text content_hash "sha256, UNIQUE"
        int width
        int height
        double noise_variance
        text routing_message
        boolean was_bypassed
        double processing_time_ms
        int storage_version "default 1"
        int schema_version "default 1"
        timestamptz created_at
        timestamptz completed_at
        timestamptz deleted_at
        uuid deleted_by
    }

    SCAN_OUTPUTS {
        uuid id PK
        uuid scan_id FK
        text type "ORIGINAL | NOISE_MAP | UNET | ENHANCED"
        uuid object_id FK "objects.id"
    }

    OBJECTS {
        uuid id PK
        text bucket
        text object_key
        text etag
        bigint size_bytes
        text mime_type
        text checksum "sha256"
        text storage_class "STANDARD | GLACIER"
        boolean encrypted "server-side SSE"
        text lifecycle_state "ACTIVE | ARCHIVED | DELETED"
        timestamptz archived_at
        timestamptz created_at
        timestamptz deleted_at
        uuid deleted_by
    }

    MODEL_VERSIONS {
        uuid id PK
        text model_name "n2n_unet"
        text model_version "v1.0.0"
        text git_commit
        text gpu_name
        jsonb params_json
        timestamptz created_at
    }

    JOBS {
        uuid id PK
        uuid scan_id FK
        text status "QUEUED | RUNNING | FAILED | RETRYING | COMPLETED | CANCELLED"
        int attempt "default 0"
        int max_attempts "default 3"
        text worker_id
        text error
        text trace_id "W3C trace for correlation"
        timestamptz created_at
        timestamptz started_at
        timestamptz finished_at
        timestamptz next_retry_at
    }

    AUDIT_LOGS {
        uuid id PK
        uuid organization_id FK
        uuid user_id FK "NULL = anonymous"
        text action "REGISTER | LOGIN | REFRESH | UPLOAD | DOWNLOAD | DELETE"
        text resource_type "scan | object | user | organization"
        uuid resource_id
        inet ip
        text user_agent
        text trace_id
        timestamptz created_at
    }

    ORGANIZATIONS ||--o{ USERS : "has"
    USERS ||--|| CREDENTIALS : "auth"
    ORGANIZATIONS ||--o{ SCANS : "owns"
    USERS ||--o{ SCANS : "submits"
    SCANS ||--o{ SCAN_OUTPUTS : "produces"
    SCAN_OUTPUTS }o--|| OBJECTS : "points to"
    SCANS }o--o| MODEL_VERSIONS : "used model"
    SCANS ||--o{ JOBS : "tracked by"
    ORGANIZATIONS ||--o{ AUDIT_LOGS : "scope"
    USERS ||--o{ AUDIT_LOGS : "generates"
```

## Indexes (migration creates these)

| Table | Index | Purpose |
|---|---|---|
| users | `uq_users_email` (email) | login lookup — UNIQUE |
| users | `ix_users_organization_id` | org membership |
| scans | `ix_scans_user_id_created_at` (user_id, created_at DESC) | paginated history |
| scans | `uq_scans_content_hash` (content_hash) | dedup — UNIQUE |
| scans | `ix_scans_status` | scheduler + admin |
| scans | `ix_scans_deleted_at` | soft-delete purge (30d) |
| scan_outputs | `uq_scan_outputs_scan_type` (scan_id, type) | one output per type |
| objects | `ix_objects_object_key` | object lookup |
| objects | `ix_objects_lifecycle_state` | archive/delete sweep |
| jobs | `ix_jobs_status_created_at` | retry scheduler |
| jobs | `ix_jobs_scan_id` | scan → job |
| audit_logs | `ix_audit_logs_user_id_created_at` | audit trail queries |
| model_versions | `ix_model_versions_name_version` | model pinning |

## Notes

- **`scan_outputs` is normalized** — adding super-resolution, segmentation, or a
  report PDF later means inserting new `type` rows, never a schema migration.
- **`objects` is storage-agnostic** — bucket/key/etag/checksum only; moving
  MinIO → S3 → R2 touches no other table.
- **`credentials` split from `users`** — OAuth/SSO/LDAP later adds providers
  without touching `users.password_hash` (it doesn't exist there).
- **`organizations` present from day one** — a solo user is an org of one;
  multi-tenant hospital onboarding needs no migration.
- **`jobs.trace_id` + `audit_logs.trace_id`** enable end-to-end correlation
  (API → RabbitMQ → worker → S3 → DB).
- All UUIDs are generated with `gen_random_uuid()` (PG 13+); `citext` and `inet`
  types require `citext` (default in many images) / native `inet`.

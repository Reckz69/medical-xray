"""Application settings loaded from environment / .env via pydantic-settings.

Every secret and knob flows through here so components never read env vars
directly. See `.env.example` at the repository root for the full list.
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── General ──────────────────────────────────────────────────────────────
    app_name: str = "Denoise X"
    environment: str = "development"  # development | staging | production
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Release provenance exposed by /health/infra (Sprint 4F). `git_sha` can be
    # injected by CI/build pipelines; when empty it is auto-detected once at
    # import time from the repository (never per request).
    app_version: str = "0.1.0"
    git_sha: str = ""

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://denoise:denoise@localhost:5433/denoise"
    )

    # ── Redis ────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── RabbitMQ ─────────────────────────────────────────────────────────────
    rabbitmq_url: str = "amqp://denoise:denoise@localhost:5672/"

    # ── Auth / JWT ───────────────────────────────────────────────────────────
    jwt_secret: str = "change-me-in-prod-0123456789abcdef"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "denoise-x"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # ── Refresh cookie ───────────────────────────────────────────────────────
    refresh_cookie_name: str = "refresh_token"
    refresh_cookie_path: str = "/api/v1/auth"
    refresh_cookie_secure: bool = False  # True in staging / production
    refresh_cookie_samesite: str = "lax"

    # ── Object storage ───────────────────────────────────────────────────────
    storage_provider: str = "minio"  # minio | s3 | azure | r2
    s3_endpoint: str = "http://localhost:9000"
    # Public endpoint used to build presigned download URLs (Sprint 4E). The
    # app talks to s3_endpoint over the compose network; browsers cannot reach
    # that internal hostname, so presigned URLs are generated against a public
    # host (e.g. https://s3.localhost locally, https://s3.<SITE_DOMAIN> in the
    # cloud) that routes to the same bucket via the Caddy edge (ADR-013).
    # Empty → presign against s3_endpoint (internal/tooling behavior).
    s3_public_endpoint: str = ""
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "denoise-xray"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False
    s3_server_side_encryption: bool = False  # SSE-KMS on S3; MinIO SSE locally
    storage_presign_expires_seconds: int = 900

    # ── Object lifecycle (days) ──────────────────────────────────────────────
    object_archive_days: int = 30
    object_delete_days: int = 365

    # ── Scheduler / job resilience ───────────────────────────────────────────
    job_stall_timeout_seconds: int = 600  # RUNNING beyond this -> recovered
    job_retry_backoff_base_seconds: int = 30  # attempt n -> base * 2^(n-1), capped
    job_retry_backoff_max_seconds: int = 3600
    scheduler_poll_interval_seconds: int = 30  # retry/republish cadence
    scheduler_cleanup_interval_seconds: int = 3600  # purge + lifecycle cadence
    scheduler_cleanup_lock_ttl_seconds: int = 3600  # Redis distributed lock TTL
    scan_purge_days: int = 30  # soft-deleted scans hard-deleted after this
    cleanup_batch_size: int = 100

    # ── Worker heartbeat / infra health (Sprint 4F) ──────────────────────────
    # The worker re-affirms a heartbeat key every interval with this TTL; the
    # gateway aggregates it into /health/infra. Crashes are handled by expiry:
    # a stopped worker's key lapses and the gateway prunes it from the registry.
    worker_heartbeat_interval_seconds: int = 10
    worker_heartbeat_ttl_seconds: int = 30

    # Gate /health/infra (operational details: worker status, model version,
    # queue depth) behind authentication. Defaults to ON in production, open in
    # development/staging unless explicitly overridden. None -> auto by env.
    health_infra_auth: bool | None = None

    # ── Rate limits (per-window) ─────────────────────────────────────────────
    rate_limit_login_per_minute: int = 5
    rate_limit_register_per_day: int = 3
    rate_limit_upload_per_hour: int = 20
    rate_limit_download_per_hour: int = 300

    # ── Feature flags (see core/feature_flags.py) ────────────────────────────
    enable_signup: bool = True
    enable_dicom: bool = True
    enable_super_resolution: bool = False
    enable_ai_report: bool = False

    # ── Observability (Sprint 4B, ADR-010) ───────────────────────────────────
    # OTel SDK wiring (spans + traceparent propagation). When False every
    # observability component is a no-op; no collector/Jaeger is required.
    otel_enabled: bool = False

    # OTel tracing exporter. "otlp-http" sends spans to otel_endpoint (the
    # collector, or a trace backend directly); "console" prints spans to stdout
    # for local debugging. The collector is the config-only abstraction for the
    # trace backend (ADR-010) — swapping Tempo/Jaeger changes only this value.
    otel_exporter: str = "otlp-http"
    otel_endpoint: str = "http://collector:4318"

    # Prometheus metrics. When True the gateway serves /metrics on the app
    # port and the worker/scheduler run a metrics HTTP server on metrics_port.
    metrics_enabled: bool = False
    metrics_port: int = 9101  # worker/scheduler scrape port

    # ── Upload validation ────────────────────────────────────────────────────
    max_upload_size_mb: int = 50
    min_image_dimension: int = 64
    max_image_dimension: int = 8192

    # ── Model (worker) ───────────────────────────────────────────────────────
    model_path: str = (
        "../n2n_unet_best_weights04.keras"  # relative to the backend dir
    )
    model_name: str = "n2n_unet"
    model_version: str = "v1.0.0"
    model_tile: int = 256
    noise_threshold: float = 8.0

    # ── CORS ─────────────────────────────────────────────────────────────────
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ]

    @model_validator(mode="after")
    def _default_health_infra_auth(self) -> "Settings":
        """Default /health/infra auth to ON in production only."""
        if self.health_infra_auth is None:
            self.health_infra_auth = self.environment == "production"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

"""Application settings loaded from environment / .env via pydantic-settings.

Every secret and knob flows through here so components never read env vars
directly. See `.env.example` at the repository root for the full list.
"""

from functools import lru_cache

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

    # ── Upload validation ────────────────────────────────────────────────────
    max_upload_size_mb: int = 50
    min_image_dimension: int = 64
    max_image_dimension: int = 8192

    # ── Model (worker) ───────────────────────────────────────────────────────
    model_path: str = (
        "../n2n_unet_best_weights04 (2).keras"  # relative to the backend dir
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

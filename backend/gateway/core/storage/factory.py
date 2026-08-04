"""Storage provider factory.

Provider is chosen once from `settings.storage_provider` and cached for the
process lifetime. `minio`, `s3`, and `r2` share the S3-compatible client;
`azure` is not implemented yet and raises a loud error rather than silently
misbehaving.
"""

from __future__ import annotations

from functools import lru_cache

from gateway.core.config import settings
from gateway.core.storage.base import StorageProvider
from gateway.core.storage.minio_provider import MinioStorageProvider


@lru_cache
def get_storage_provider() -> StorageProvider:
    provider = settings.storage_provider
    if provider in ("minio", "s3", "r2"):
        return MinioStorageProvider(settings)
    raise NotImplementedError(
        f"storage provider {provider!r} is not implemented yet "
        "(implemented: minio, s3, r2)"
    )


#: Process-wide singleton; most code imports this instead of the factory.
storage = get_storage_provider()

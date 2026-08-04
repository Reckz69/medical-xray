"""Object-storage abstraction.

Storage is bucket/key/etag/checksum only — the `objects` table is
storage-agnostic, so moving MinIO -> S3 -> R2 touches no other code. See
ADR-003. Images are never proxied through the gateway: downloads use
presigned URLs (server-side SSE at rest, per `settings.s3_server_side_encryption`).
"""

from gateway.core.storage.base import StorageObject, StorageProvider
from gateway.core.storage.factory import get_storage_provider, storage

__all__ = [
    "StorageObject",
    "StorageProvider",
    "get_storage_provider",
    "storage",
]

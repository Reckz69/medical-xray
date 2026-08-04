"""Storage provider contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class StorageObject:
    """Metadata about a stored object (mirrors the `objects` table)."""

    bucket: str
    object_key: str
    size_bytes: int
    mime_type: str = "application/octet-stream"
    etag: str | None = None
    checksum: str | None = None
    extra: dict = field(default_factory=dict)


class StorageProvider(ABC):
    """Interface implemented by MinIO/S3/R2/Azure backends."""

    @abstractmethod
    async def ensure_bucket(self) -> None:
        """Create the configured bucket if it does not exist."""

    @abstractmethod
    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        checksum: str | None = None,
    ) -> StorageObject:
        """Store bytes under `key` and return the resulting metadata."""

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Fetch the full object bytes for `key`."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Permanently remove the object at `key` (used after retention)."""

    @abstractmethod
    async def presign_get(self, key: str, expires_seconds: int | None = None) -> str:
        """Return a short-lived URL to read `key` (ADR-003)."""

"""MinIO/S3/R2 provider backed by the `minio` client.

The MinIO Python SDK speaks S3, so it also serves AWS S3 and Cloudflare R2
(any S3-compatible endpoint). Azure uses a separate provider (not yet added).
All blocking I/O is dispatched to a worker thread via `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import datetime
from io import BytesIO
from typing import Any

from minio import Minio

from gateway.core.config import Settings
from gateway.core.storage.base import StorageObject, StorageProvider


def _endpoint_from_url(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").rstrip("/")


class MinioStorageProvider(StorageProvider):
    def __init__(self, settings: Settings) -> None:
        self._client = Minio(
            _endpoint_from_url(settings.s3_endpoint),
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            secure=settings.s3_use_ssl,
            region=settings.s3_region,
        )
        self.bucket = settings.s3_bucket
        self._presign_expires = settings.storage_presign_expires_seconds

    async def ensure_bucket(self) -> None:
        def _ensure() -> None:
            if not self._client.bucket_exists(self.bucket):
                self._client.make_bucket(self.bucket)

        await asyncio.to_thread(_ensure)

    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        checksum: str | None = None,
    ) -> StorageObject:
        def _upload() -> StorageObject:
            result = self._client.put_object(
                self.bucket,
                key,
                BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            return StorageObject(
                bucket=self.bucket,
                object_key=key,
                size_bytes=len(data),
                mime_type=content_type,
                etag=result.etag,
                checksum=checksum,
            )

        return await asyncio.to_thread(_upload)

    async def download(self, key: str) -> bytes:
        def _download() -> bytes:
            response = self._client.get_object(self.bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return await asyncio.to_thread(_download)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.remove_object, self.bucket, key)

    async def presign_get(self, key: str, expires_seconds: int | None = None) -> str:
        expires = datetime.timedelta(seconds=expires_seconds or self._presign_expires)
        return await asyncio.to_thread(
            self._client.presigned_get_object,
            self.bucket,
            key,
            expires=expires,
        )


def build_minio_provider(settings: Settings, **_kwargs: Any) -> MinioStorageProvider:
    return MinioStorageProvider(settings)

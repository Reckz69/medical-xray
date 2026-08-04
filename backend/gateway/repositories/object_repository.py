"""Object + ScanOutput persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from gateway.models.scan import (
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_DELETED,
    Object,
    ScanOutput,
)
from gateway.repositories.base import BaseRepository


class ObjectRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(
        self,
        *,
        bucket: str,
        object_key: str,
        size_bytes: int,
        mime_type: str,
        checksum: str | None = None,
        etag: str | None = None,
        encrypted: bool = False,
    ) -> Object:
        obj = Object(
            bucket=bucket,
            object_key=object_key,
            size_bytes=size_bytes,
            mime_type=mime_type,
            checksum=checksum,
            etag=etag,
            encrypted=encrypted,
        )
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get_by_id(self, object_id: UUID) -> Object | None:
        return await self.session.get(Object, object_id)

    async def get_by_key(self, object_key: str) -> Object | None:
        result = await self.session.execute(
            select(Object).where(Object.object_key == object_key)
        )
        return result.scalar_one_or_none()

    async def archive(self, object_id: UUID) -> Object | None:
        obj = await self.session.get(Object, object_id)
        if obj is not None:
            obj.lifecycle_state = LIFECYCLE_ARCHIVED
            obj.archived_at = datetime.now(UTC)
            obj.storage_class = "GLACIER"
            await self.session.flush()
        return obj

    async def mark_deleted(self, object_id: UUID, deleted_by: UUID) -> Object | None:
        obj = await self.session.get(Object, object_id)
        if obj is not None:
            obj.lifecycle_state = LIFECYCLE_DELETED
            obj.deleted_at = datetime.now(UTC)
            obj.deleted_by = deleted_by
            await self.session.flush()
        return obj


class ScanOutputRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def add(self, *, scan_id: UUID, type: str, object_id: UUID) -> ScanOutput:
        output = ScanOutput(scan_id=scan_id, type=type, object_id=object_id)
        self.session.add(output)
        await self.session.flush()
        return output

    async def get_for_scan(self, scan_id: UUID, type: str) -> ScanOutput | None:
        result = await self.session.execute(
            select(ScanOutput).where(
                ScanOutput.scan_id == scan_id, ScanOutput.type == type
            )
        )
        return result.scalar_one_or_none()

    async def list_for_scan(self, scan_id: UUID) -> list[ScanOutput]:
        result = await self.session.execute(
            select(ScanOutput)
            .options(joinedload(ScanOutput.object))
            .where(ScanOutput.scan_id == scan_id)
            .order_by(ScanOutput.type)
        )
        return list(result.scalars().all())

"""Scan persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from gateway.models.job import Job
from gateway.models.scan import (
    SCAN_STATUS_CANCELLED,
    SCAN_STATUS_RUNNING,
    Object,
    Scan,
    ScanOutput,
)
from gateway.repositories.base import BaseRepository

_SCAN_LOADS = (
    selectinload(Scan.outputs).selectinload(ScanOutput.object),
    selectinload(Scan.model_version),
)


class ScanRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._active = Scan.deleted_at.is_(None)

    async def create(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        original_name: str,
        format: str,
        size_bytes: int,
        content_hash: str,
        width: int,
        height: int,
        status: str,
    ) -> Scan:
        scan = Scan(
            organization_id=organization_id,
            user_id=user_id,
            original_name=original_name,
            format=format,
            size_bytes=size_bytes,
            content_hash=content_hash,
            width=width,
            height=height,
            status=status,
        )
        self.session.add(scan)
        await self.session.flush()
        return scan

    async def get_by_id(self, scan_id: UUID) -> Scan | None:
        return await self.session.get(Scan, scan_id)

    async def get_with_outputs(self, scan_id: UUID) -> Scan | None:
        result = await self.session.execute(
            select(Scan)
            .options(*_SCAN_LOADS)
            .where(Scan.id == scan_id)
        )
        return result.scalar_one_or_none()

    async def get_owned_by(self, scan_id: UUID, user_id: UUID) -> Scan | None:
        result = await self.session.execute(
            select(Scan)
            .options(*_SCAN_LOADS)
            .where(
                Scan.id == scan_id,
                Scan.user_id == user_id,
                self._active,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_by_org_and_hash(
        self, organization_id: UUID, content_hash: str
    ) -> Scan | None:
        """Return an active scan with the same bytes in this organization.

        Drives idempotent upload dedup: a matching scan is reused instead of
        re-uploading the object or enqueueing a new job.
        """
        result = await self.session.execute(
            select(Scan)
            .options(*_SCAN_LOADS)
            .where(
                Scan.organization_id == organization_id,
                Scan.content_hash == content_hash,
                self._active,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Scan]:
        result = await self.session.execute(
            select(Scan)
            .options(*_SCAN_LOADS)
            .where(Scan.user_id == user_id, self._active)
            .order_by(Scan.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_for_user(self, user_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count(Scan.id)).where(
                Scan.user_id == user_id, self._active
            )
        )
        return int(result.scalar_one() or 0)

    async def soft_delete(self, scan_id: UUID, deleted_by: UUID) -> Scan | None:
        scan = await self.session.get(Scan, scan_id)
        if scan is not None:
            scan.deleted_at = datetime.now(UTC)
            scan.deleted_by = deleted_by
            await self.session.flush()
        return scan

    async def set_running(self, scan_id: UUID) -> Scan | None:
        scan = await self.session.get(Scan, scan_id)
        if scan is not None:
            scan.status = SCAN_STATUS_RUNNING
            await self.session.flush()
        return scan

    async def set_completed(
        self,
        scan_id: UUID,
        *,
        model_id: UUID | None,
        noise_variance: float | None,
        processing_time_ms: float | None,
        routing_message: str | None = None,
        was_bypassed: bool | None = None,
        status: str,
    ) -> Scan | None:
        scan = await self.session.get(Scan, scan_id)
        if scan is None:
            return None
        scan.model_id = model_id
        scan.noise_variance = noise_variance
        scan.processing_time_ms = processing_time_ms
        if routing_message is not None:
            scan.routing_message = routing_message
        if was_bypassed is not None:
            scan.was_bypassed = was_bypassed
        scan.status = status
        scan.completed_at = datetime.now(UTC)
        await self.session.flush()
        return scan

    async def set_failed(self, scan_id: UUID, *, routing_message: str) -> Scan | None:
        scan = await self.session.get(Scan, scan_id)
        if scan is None:
            return None
        scan.routing_message = routing_message
        scan.status = "FAILED"
        await self.session.flush()
        return scan

    async def set_cancelled(self, scan_id: UUID) -> Scan | None:
        scan = await self.session.get(Scan, scan_id)
        if scan is None:
            return None
        scan.status = SCAN_STATUS_CANCELLED
        await self.session.flush()
        return scan

    async def list_purgeable(
        self, cutoff: datetime, *, limit: int = 100
    ) -> list[Scan]:
        """Soft-deleted scans past the retention window, oldest first (ADR-009)."""
        result = await self.session.execute(
            select(Scan)
            .options(selectinload(Scan.outputs).selectinload(ScanOutput.object))
            .where(
                Scan.deleted_at.is_not(None),
                Scan.deleted_at < cutoff,
            )
            .order_by(Scan.deleted_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def purge(self, scan_id: UUID) -> Scan | None:
        """Hard-delete a scan, its jobs, output rows, and output objects."""
        scan = await self.session.get(
            Scan,
            scan_id,
            options=(selectinload(Scan.outputs).selectinload(ScanOutput.object),),
        )
        if scan is None:
            return None
        object_ids = [output.object_id for output in scan.outputs if output.object_id]
        await self.session.execute(delete(Job).where(Job.scan_id == scan_id))
        await self.session.delete(scan)
        await self.session.flush()
        for object_id in object_ids:
            obj = await self.session.get(Object, object_id)
            if obj is not None:
                await self.session.delete(obj)
        await self.session.flush()
        return scan

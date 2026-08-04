"""Audit log persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.models.audit import AuditLog
from gateway.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(
        self,
        *,
        action: str,
        organization_id: UUID | None = None,
        user_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> AuditLog:
        log = AuditLog(
            action=action,
            organization_id=organization_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            ip=ip,
            user_agent=user_agent,
            trace_id=trace_id,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        result = await self.session.execute(
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

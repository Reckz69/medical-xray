"""Organization persistence."""

from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from gateway.models.organization import Organization
from gateway.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(self, name: str) -> Organization:
        org = Organization(name=name)
        self.session.add(org)
        await self.session.flush()
        return org

    async def get_by_id(self, org_id: UUID) -> Organization | None:
        return await self.session.get(Organization, org_id)

    @staticmethod
    def next_id() -> UUID:
        return uuid.uuid4()

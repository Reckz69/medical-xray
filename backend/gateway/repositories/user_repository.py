"""User persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.models.user import STATUS_ACTIVE, User
from gateway.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._active = User.deleted_at.is_(None)

    async def create(
        self,
        *,
        organization_id: UUID,
        email: str,
        name: str,
        role: str,
    ) -> User:
        user = User(
            organization_id=organization_id,
            email=email,
            name=name,
            role=role,
            status=STATUS_ACTIVE,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_active_by_id(self, user_id: UUID) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id, self._active)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email, self._active)
        )
        return result.scalar_one_or_none()

    async def touch_last_login(self, user_id: UUID) -> None:
        user = await self.session.get(User, user_id)
        if user is not None:
            user.last_login_at = datetime.now(UTC)
            await self.session.flush()

    async def soft_delete(self, user_id: UUID, deleted_by: UUID) -> None:
        user = await self.session.get(User, user_id)
        if user is not None:
            user.deleted_at = datetime.now(UTC)
            user.deleted_by = deleted_by
            user.status = "suspended"
            await self.session.flush()

    @staticmethod
    def next_id() -> UUID:
        return uuid.uuid4()

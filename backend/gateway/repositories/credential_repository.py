"""Credential persistence (1:1 with users, auth material only)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.models.user import Credential
from gateway.repositories.base import BaseRepository


class CredentialRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_user_id(self, user_id: UUID) -> Credential | None:
        return await self.session.get(Credential, user_id)

    async def upsert_password(self, user_id: UUID, password_hash: str) -> Credential:
        credential = await self.session.get(Credential, user_id)
        if credential is None:
            credential = Credential(user_id=user_id, password_hash=password_hash)
            self.session.add(credential)
        else:
            credential.password_hash = password_hash
        await self.session.flush()
        return credential

    async def get_refresh_version(self, user_id: UUID) -> int:
        result = await self.session.execute(
            select(Credential.refresh_token_version).where(
                Credential.user_id == user_id
            )
        )
        value = result.scalar_one_or_none()
        return int(value or 0)

    async def bump_refresh_version(self, user_id: UUID) -> int:
        """Rotate the token family (logout / refresh); returns the new version."""
        credential = await self.session.get(Credential, user_id)
        if credential is None:
            return 0
        credential.refresh_token_version += 1
        await self.session.flush()
        return credential.refresh_token_version

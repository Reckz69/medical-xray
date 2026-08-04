"""ModelVersion persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.models.model_version import ModelVersion
from gateway.repositories.base import BaseRepository


class ModelVersionRepository(BaseRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(
        self,
        *,
        model_name: str,
        model_version: str,
        git_commit: str | None = None,
        gpu_name: str | None = None,
        params_json: dict | None = None,
    ) -> ModelVersion:
        mv = ModelVersion(
            model_name=model_name,
            model_version=model_version,
            git_commit=git_commit,
            gpu_name=gpu_name,
            params_json=params_json or {},
        )
        self.session.add(mv)
        await self.session.flush()
        return mv

    async def get_by_id(self, model_id) -> ModelVersion | None:
        return await self.session.get(ModelVersion, model_id)

    async def get_latest(self, model_name: str) -> ModelVersion | None:
        result = await self.session.execute(
            select(ModelVersion)
            .where(ModelVersion.model_name == model_name)
            .order_by(ModelVersion.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_name_version(
        self, model_name: str, model_version: str
    ) -> ModelVersion | None:
        result = await self.session.execute(
            select(ModelVersion).where(
                ModelVersion.model_name == model_name,
                ModelVersion.model_version == model_version,
            )
        )
        return result.scalar_one_or_none()

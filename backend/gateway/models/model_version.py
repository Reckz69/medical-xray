"""ModelVersion — pinned inference artifacts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from gateway.models.scan import Scan


class ModelVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        Index("ix_model_versions_name_version", "model_name", "model_version"),
    )

    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gpu_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    params_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    scans: Mapped[list[Scan]] = relationship(back_populates="model_version")

"""AuditLog — append-only action trail with end-to-end trace correlation."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from gateway.models.organization import Organization
    from gateway.models.user import User

ACTION_REGISTER = "REGISTER"
ACTION_LOGIN = "LOGIN"
ACTION_REFRESH = "REFRESH"
ACTION_UPLOAD = "UPLOAD"
ACTION_DOWNLOAD = "DOWNLOAD"
ACTION_DELETE = "DELETE"


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_id_created_at", "user_id", "created_at"),
    )

    organization_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=True,  # anonymous actions (e.g. REGISTER) have no org scope yet
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    organization: Mapped[Organization | None] = relationship(back_populates="audit_logs")
    user: Mapped[User | None] = relationship(back_populates="audit_logs")

"""Organization — every user belongs to one (solo users are orgs of one)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.models.base import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from gateway.models.audit import AuditLog
    from gateway.models.scan import Scan
    from gateway.models.user import User

#: Default per-org storage quota (5 GiB).
DEFAULT_STORAGE_LIMIT_BYTES = 5 * 1024 * 1024 * 1024

PLAN_FREE = "free"
PLAN_PRO = "pro"


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text(f"'{PLAN_FREE}'")
    )
    storage_limit_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=str(DEFAULT_STORAGE_LIMIT_BYTES)
    )

    users: Mapped[list[User]] = relationship(
        back_populates="organization", foreign_keys="User.organization_id"
    )
    scans: Mapped[list[Scan]] = relationship(back_populates="organization")
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="organization")

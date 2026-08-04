"""User + Credential.

`credentials` is split from `users` so OAuth/SSO/LDAP can be added later
without touching this table.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateway.models.base import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from gateway.models.audit import AuditLog
    from gateway.models.organization import Organization
    from gateway.models.scan import Scan

ROLE_PATIENT = "patient"
ROLE_RADIOLOGIST = "radiologist"
ROLE_ADMIN = "admin"

STATUS_ACTIVE = "active"
STATUS_SUSPENDED = "suspended"


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_organization_id", "organization_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text(f"'{ROLE_PATIENT}'")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text(f"'{STATUS_ACTIVE}'")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    organization: Mapped[Organization] = relationship(
        back_populates="users", foreign_keys=[organization_id]
    )
    credential: Mapped[Credential | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    scans: Mapped[list[Scan]] = relationship(
        back_populates="user", foreign_keys="Scan.user_id"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="user")


class Credential(Base):
    """1:1 with users; holds auth material only."""

    __tablename__ = "credentials"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    refresh_token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    mfa_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="credential")

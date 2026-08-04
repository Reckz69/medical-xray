"""Repositories — the persistence layer.

Each repository wraps an `AsyncSession` and returns ORM objects only; services
apply business rules. Pattern: Router → Service → Repository.
"""

from gateway.repositories.audit_repository import AuditLogRepository
from gateway.repositories.base import BaseRepository
from gateway.repositories.credential_repository import CredentialRepository
from gateway.repositories.job_repository import JobRepository
from gateway.repositories.model_repository import ModelVersionRepository
from gateway.repositories.object_repository import (
    ObjectRepository,
    ScanOutputRepository,
)
from gateway.repositories.organization_repository import OrganizationRepository
from gateway.repositories.scan_repository import ScanRepository
from gateway.repositories.user_repository import UserRepository

__all__ = [
    "AuditLogRepository",
    "BaseRepository",
    "CredentialRepository",
    "JobRepository",
    "ModelVersionRepository",
    "ObjectRepository",
    "OrganizationRepository",
    "ScanOutputRepository",
    "ScanRepository",
    "UserRepository",
]

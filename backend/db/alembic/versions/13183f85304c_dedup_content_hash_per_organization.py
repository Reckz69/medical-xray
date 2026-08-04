"""dedup content_hash per organization

Content-hash dedup must be scoped to the tenancy boundary: identical bytes are
re-usable within an organization (idempotent re-upload) but must not collide
across organizations. This replaces the global ``uq_scans_content_hash``
constraint with a partial unique index on ``(organization_id, content_hash)``
that only constrains active rows, so a soft-deleted scan can be re-uploaded.

Revision ID: 13183f85304c
Revises: 3f9d24b11bea
Create Date: 2026-08-05 03:53:11.312761

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "13183f85304c"
down_revision: str | Sequence[str] | None = "3f9d24b11bea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("uq_scans_content_hash", "scans", type_="unique")
    op.create_index(
        "uq_scans_org_content_hash_active",
        "scans",
        ["organization_id", "content_hash"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_scans_org_content_hash_active", table_name="scans")
    op.create_unique_constraint("uq_scans_content_hash", "scans", ["content_hash"])

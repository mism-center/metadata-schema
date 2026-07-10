"""Rename resources.status -> version_status; add registration_status workflow field.

Revision ID: 006
Revises: 005
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# New enum type for the AI-augmented registration workflow.
registrationstatus = sa.Enum(
    "draft",
    "annotating",
    "annotation_failed",
    "pending_review",
    "rejected",
    "approved",
    name="resourceregistrationstatus",
)


def upgrade() -> None:
    # 1. Rename the version-lifecycle column + its index (PG enum type
    #    "resourcestatus" is unchanged — only the column name moves).
    op.alter_column("resources", "status", new_column_name="version_status")
    op.execute("ALTER INDEX ix_resources_status RENAME TO ix_resources_version_status")

    # 2. New registration_status column. Existing rows backfill to 'approved'
    #    (they predate the workflow and are already in use).
    registrationstatus.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "resources",
        sa.Column(
            "registration_status",
            registrationstatus,
            nullable=False,
            server_default="approved",
        ),
    )
    op.create_index("ix_resources_registration_status", "resources", ["registration_status"])


def downgrade() -> None:
    op.drop_index("ix_resources_registration_status", table_name="resources")
    op.drop_column("resources", "registration_status")
    registrationstatus.drop(op.get_bind(), checkfirst=True)

    op.execute("ALTER INDEX ix_resources_version_status RENAME TO ix_resources_status")
    op.alter_column("resources", "version_status", new_column_name="status")

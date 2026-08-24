"""Add Dockerfile/image review workflow + metadata-reviewer identity tracking (MISM-291).

Revision ID: 008
Revises: 007
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: str = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

imagereviewstatus = sa.Enum(
    "not_applicable",
    "pending_image_check",
    "image_approved",
    "image_rejected",
    name="imagereviewstatus",
)


def upgrade() -> None:
    # Metadata-review reviewer identity/reason — the existing registration_status
    # workflow gets these for the first time (previously unattributed).
    op.add_column(
        "resources", sa.Column("metadata_reviewed_by", sa.String(255), server_default="")
    )
    op.add_column(
        "resources", sa.Column("metadata_reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "resources", sa.Column("metadata_rejection_reason", sa.Text(), server_default="")
    )

    # New Dockerfile/image review workflow.
    imagereviewstatus.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "resources",
        sa.Column(
            "image_review_status",
            imagereviewstatus,
            nullable=False,
            server_default="not_applicable",
        ),
    )
    op.add_column("resources", sa.Column("image_reviewed_by", sa.String(255), server_default=""))
    op.add_column(
        "resources", sa.Column("image_reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("resources", sa.Column("image_rejection_reason", sa.Text(), server_default=""))
    op.create_index("ix_resources_image_review_status", "resources", ["image_review_status"])


def downgrade() -> None:
    op.drop_index("ix_resources_image_review_status", table_name="resources")
    op.drop_column("resources", "image_rejection_reason")
    op.drop_column("resources", "image_reviewed_at")
    op.drop_column("resources", "image_reviewed_by")
    op.drop_column("resources", "image_review_status")
    imagereviewstatus.drop(op.get_bind(), checkfirst=True)

    op.drop_column("resources", "metadata_rejection_reason")
    op.drop_column("resources", "metadata_reviewed_at")
    op.drop_column("resources", "metadata_reviewed_by")

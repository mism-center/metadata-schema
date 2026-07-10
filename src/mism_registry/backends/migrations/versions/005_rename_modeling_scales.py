"""Rename resources.modeling_scales -> model_scales (align with schema.md).

Revision ID: 005
Revises: 004
Create Date: 2026-07-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "005"
down_revision: str = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("resources", "modeling_scales", new_column_name="model_scales")
    op.execute("ALTER INDEX ix_resources_modeling_scales RENAME TO ix_resources_model_scales")


def downgrade() -> None:
    op.execute("ALTER INDEX ix_resources_model_scales RENAME TO ix_resources_modeling_scales")
    op.alter_column("resources", "model_scales", new_column_name="modeling_scales")

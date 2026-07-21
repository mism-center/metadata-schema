"""Add runs.entrypoint and runs.container (JSONB, denormalized from the model).

Revision ID: 007
Revises: 006
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "007"
down_revision: str = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable — existing runs predate entry-point selection.
    op.add_column("runs", sa.Column("entrypoint", JSONB, nullable=True))
    op.add_column("runs", sa.Column("container", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "container")
    op.drop_column("runs", "entrypoint")

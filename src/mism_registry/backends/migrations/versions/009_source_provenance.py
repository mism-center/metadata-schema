"""Add source provenance for upstream-imported resources.

Revision ID: 009
Revises: 008
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: str = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("resources", sa.Column("source_repository", sa.String(100), server_default=""))
    op.add_column("resources", sa.Column("source_identifier", sa.String(255), server_default=""))
    op.add_column("resources", sa.Column("source_url", sa.Text(), server_default=""))
    op.add_column("resources", sa.Column("source_revision", sa.String(100), server_default=""))

    # One catalogued copy per upstream model. Unapproved rows are excluded so an
    # in-flight import by one user does not bar another from importing the same
    # model; the collision surfaces when the second one is approved.
    # The <> '' predicate confines the constraint to imported rows; existing rows
    # backfill to '' and would otherwise all collide on ('', '').
    op.create_index(
        "uq_resources_source",
        "resources",
        ["source_repository", "source_identifier"],
        unique=True,
        postgresql_where=sa.text(
            "source_repository <> '' AND source_identifier <> '' "
            "AND registration_status = 'approved'"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_resources_source", table_name="resources")
    op.drop_column("resources", "source_revision")
    op.drop_column("resources", "source_url")
    op.drop_column("resources", "source_identifier")
    op.drop_column("resources", "source_repository")

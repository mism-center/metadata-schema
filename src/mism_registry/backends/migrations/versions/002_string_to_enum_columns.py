"""Convert string columns to native PostgreSQL enum types.

Revision ID: 002
Revises: 001
Create Date: 2026-03-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Enum definitions matching mism_registry.enums
resourcetype = sa.Enum("dataset", "model", "tool", name="resourcetype")
executiontype = sa.Enum(
    "docker",
    "conda",
    "python",
    "r",
    "binary",
    "huggingface",
    "notebook",
    "other",
    name="executiontype",
)
resourcestatus = sa.Enum("active", "superseded", "archived", name="resourcestatus")
runstatus = sa.Enum(
    "registered",
    "running",
    "completed",
    "failed",
    "cancelled",
    name="runstatus",
)


def upgrade() -> None:
    # Create enum types
    resourcetype.create(op.get_bind(), checkfirst=True)
    executiontype.create(op.get_bind(), checkfirst=True)
    resourcestatus.create(op.get_bind(), checkfirst=True)
    runstatus.create(op.get_bind(), checkfirst=True)

    # Alter resources columns
    op.alter_column(
        "resources",
        "resource_type",
        type_=resourcetype,
        postgresql_using="resource_type::resourcetype",
        existing_nullable=False,
    )
    op.alter_column(
        "resources",
        "status",
        type_=resourcestatus,
        postgresql_using="status::resourcestatus",
        server_default="active",
        existing_nullable=False,
    )
    op.alter_column(
        "resources",
        "execution_type",
        type_=executiontype,
        postgresql_using="execution_type::executiontype",
        existing_nullable=True,
    )

    # Alter runs.status
    op.alter_column(
        "runs",
        "status",
        type_=runstatus,
        postgresql_using="status::runstatus",
        server_default="registered",
        existing_nullable=False,
    )


def downgrade() -> None:
    # Revert columns back to VARCHAR(20)
    op.alter_column(
        "runs",
        "status",
        type_=sa.String(20),
        postgresql_using="status::text",
        server_default="registered",
        existing_nullable=False,
    )
    op.alter_column(
        "resources",
        "execution_type",
        type_=sa.String(20),
        postgresql_using="execution_type::text",
        existing_nullable=True,
    )
    op.alter_column(
        "resources",
        "status",
        type_=sa.String(20),
        postgresql_using="status::text",
        server_default="active",
        existing_nullable=False,
    )
    op.alter_column(
        "resources",
        "resource_type",
        type_=sa.String(20),
        postgresql_using="resource_type::text",
        existing_nullable=False,
    )

    # Drop enum types
    runstatus.drop(op.get_bind(), checkfirst=True)
    resourcestatus.drop(op.get_bind(), checkfirst=True)
    executiontype.drop(op.get_bind(), checkfirst=True)
    resourcetype.drop(op.get_bind(), checkfirst=True)

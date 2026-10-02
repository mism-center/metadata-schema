"""Add agent environment-build status (env_build_status, env_build_error).

Revision ID: 010
Revises: 009
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: str = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

envbuildstatus = sa.Enum(
    "not_ready",
    "ready_for_build",
    "building",
    "build_failed",
    "runnable",
    name="envbuildstatus",
)


def upgrade() -> None:
    envbuildstatus.create(op.get_bind(), checkfirst=True)
    # Existing rows (incl. already-approved) stay not_ready: no surprise mass build.
    op.add_column(
        "resources",
        sa.Column(
            "env_build_status",
            envbuildstatus,
            nullable=False,
            server_default="not_ready",
        ),
    )
    op.add_column("resources", sa.Column("env_build_error", sa.Text(), server_default=""))
    op.create_index("ix_resources_env_build_status", "resources", ["env_build_status"])


def downgrade() -> None:
    op.drop_index("ix_resources_env_build_status", table_name="resources")
    op.drop_column("resources", "env_build_error")
    op.drop_column("resources", "env_build_status")
    envbuildstatus.drop(op.get_bind(), checkfirst=True)

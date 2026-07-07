"""Add schema.md annotation fields (Sections A/B/C, values only).

Revision ID: 004
Revises: 003
Create Date: 2026-07-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = "004"
down_revision: str = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# New execution_type / environment_kind enum values (schema.md Section B)
_NEW_ENUM_VALUES = [
    "pip",
    "singularity",
    "nextflow",
    "snakemake",
    "jupyter",
    "native",
]

# ARRAY(String) columns — biology + model characterization lists
_ARRAY_COLUMNS = [
    "model_class",
    "formalism",
    "infectious_agents",
    "health_conditions",
    "biological_processes",
    "molecular_entities",
    "proteins_genes",
]

# JSONB list columns (default '[]'); single-object JSONB columns are nullable
_JSONB_LIST_COLUMNS = [
    "contacts",
    "related_resources",
    "dependencies",
    "containers",
    "entry_points",
]
_JSONB_OBJ_COLUMNS = ["compute", "tests", "io"]


def upgrade() -> None:
    # 1. Extend the native enum type with the new environment_kind values.
    #    ALTER TYPE ... ADD VALUE cannot run inside a transaction block, so
    #    commit the migration's implicit transaction first.
    op.execute("COMMIT")
    for val in _NEW_ENUM_VALUES:
        op.execute(f"ALTER TYPE executiontype ADD VALUE IF NOT EXISTS '{val}'")

    # 2. Scalar text columns (server_default backfills existing rows).
    op.add_column("resources", sa.Column("short_description", sa.Text(), server_default=""))
    op.add_column("resources", sa.Column("execution_status", sa.String(50), server_default=""))
    op.add_column("resources", sa.Column("language_name", sa.String(100), server_default=""))
    op.add_column("resources", sa.Column("language_version", sa.String(100), server_default=""))
    op.add_column("resources", sa.Column("execution_notes", sa.Text(), server_default=""))
    op.add_column(
        "resources", sa.Column("determinism", sa.String(50), server_default="unknown")
    )
    op.add_column(
        "resources", sa.Column("time_dynamics", sa.String(50), server_default="unknown")
    )
    op.add_column("resources", sa.Column("spatial", sa.String(50), server_default="unknown"))
    op.add_column("resources", sa.Column("multiscale", sa.Boolean(), nullable=True))

    # 3. ARRAY(String) list columns.
    for col in _ARRAY_COLUMNS:
        op.add_column("resources", sa.Column(col, ARRAY(sa.String()), server_default="{}"))

    # 4. JSONB columns.
    for col in _JSONB_LIST_COLUMNS:
        op.add_column("resources", sa.Column(col, JSONB(), server_default="[]"))
    for col in _JSONB_OBJ_COLUMNS:
        op.add_column("resources", sa.Column(col, JSONB(), nullable=True))


def downgrade() -> None:
    # Drop added columns. Enum values are left in place — Postgres cannot
    # remove enum values without recreating the type.
    for col in _JSONB_OBJ_COLUMNS + _JSONB_LIST_COLUMNS + _ARRAY_COLUMNS:
        op.drop_column("resources", col)
    for col in [
        "multiscale",
        "spatial",
        "time_dynamics",
        "determinism",
        "execution_notes",
        "language_version",
        "language_name",
        "execution_status",
        "short_description",
    ]:
        op.drop_column("resources", col)

"""Initial schema: resources and runs tables.

Revision ID: 001
Revises:
Create Date: 2026-03-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enable pg_trgm for trigram similarity indexes
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ── resources table ──────────────────────────────────────────────
    op.create_table(
        "resources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("resource_type", sa.String(20), nullable=False),
        sa.Column("location_uri", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.String(100), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "new_version_of",
            sa.String(36),
            sa.ForeignKey("resources.id"),
            nullable=True,
        ),
        sa.Column(
            "superseded_by",
            sa.String(36),
            sa.ForeignKey("resources.id"),
            nullable=True,
        ),
        # Authorship & attribution
        sa.Column("authors", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("organization", sa.String(500), nullable=False, server_default=""),
        sa.Column("contact_email", sa.String(255), nullable=False, server_default=""),
        sa.Column("publications", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("funding", postgresql.JSONB(), nullable=False, server_default="[]"),
        # Scientific context
        sa.Column(
            "modeling_scales",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "organisms",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "domains",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("date_published", sa.Date(), nullable=True),
        # Location & integrity
        sa.Column(
            "format_tags",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("digest_sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("external_ids", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("license", sa.String(100), nullable=False, server_default=""),
        # Execution
        sa.Column("execution_type", sa.String(20), nullable=True),
        sa.Column("execution_ref", sa.Text(), nullable=False, server_default=""),
        sa.Column("io_spec", postgresql.JSONB(), nullable=True),
        # System
        sa.Column("owner", sa.String(255), nullable=False, server_default=""),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Resources indexes
    op.create_index("ix_resources_resource_type", "resources", ["resource_type"])
    op.create_index("ix_resources_status", "resources", ["status"])
    op.create_index("ix_resources_owner", "resources", ["owner"])
    op.create_index(
        "ix_resources_format_tags",
        "resources",
        ["format_tags"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_resources_organisms",
        "resources",
        ["organisms"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_resources_modeling_scales",
        "resources",
        ["modeling_scales"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_resources_domains",
        "resources",
        ["domains"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_resources_name_trgm",
        "resources",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    # ── runs table ───────────────────────────────────────────────────
    op.create_table(
        "runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "model_id",
            sa.String(36),
            sa.ForeignKey("resources.id"),
            nullable=False,
        ),
        sa.Column("model_version", sa.String(100), nullable=False, server_default=""),
        sa.Column(
            "input_resource_ids",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "output_resource_ids",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("environment", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="registered"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("log_uri", sa.Text(), nullable=False, server_default=""),
        sa.Column("triggered_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Runs indexes
    op.create_index("ix_runs_model_id", "runs", ["model_id"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_triggered_by", "runs", ["triggered_by"])
    op.create_index(
        "ix_runs_input_resource_ids",
        "runs",
        ["input_resource_ids"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_runs_output_resource_ids",
        "runs",
        ["output_resource_ids"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_table("runs")
    op.drop_table("resources")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")

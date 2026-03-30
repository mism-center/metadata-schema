"""Add tsvector search_vector column with trigger and GIN index.

Revision ID: 003
Revises: 002
Create Date: 2026-03-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRIGGER_FUNCTION = """\
CREATE OR REPLACE FUNCTION resources_search_vector_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector :=
    setweight(to_tsvector('english', coalesce(NEW.name, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.description, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(NEW.organization, '')), 'C') ||
    setweight(to_tsvector('english', coalesce(array_to_string(NEW.domains, ' '), '')), 'C') ||
    setweight(to_tsvector('english', coalesce(array_to_string(NEW.organisms, ' '), '')), 'C');
  RETURN NEW;
END
$$ LANGUAGE plpgsql;
"""

TRIGGER = """\
CREATE TRIGGER trg_resources_search_vector
  BEFORE INSERT OR UPDATE ON resources
  FOR EACH ROW EXECUTE FUNCTION resources_search_vector_update();
"""

BACKFILL = """\
UPDATE resources SET search_vector =
  setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
  setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
  setweight(to_tsvector('english', coalesce(organization, '')), 'C') ||
  setweight(to_tsvector('english', coalesce(array_to_string(domains, ' '), '')), 'C') ||
  setweight(to_tsvector('english', coalesce(array_to_string(organisms, ' '), '')), 'C');
"""


def upgrade() -> None:
    # Add the tsvector column
    op.add_column(
        "resources",
        sa.Column("search_vector", sa.dialects.postgresql.TSVECTOR(), nullable=True),
    )

    # Create trigger function and trigger
    op.execute(TRIGGER_FUNCTION)
    op.execute(TRIGGER)

    # Backfill existing rows
    op.execute(BACKFILL)

    # Create GIN index
    op.create_index(
        "ix_resources_search_vector",
        "resources",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_resources_search_vector", table_name="resources")
    op.execute("DROP TRIGGER IF EXISTS trg_resources_search_vector ON resources")
    op.execute("DROP FUNCTION IF EXISTS resources_search_vector_update()")
    op.drop_column("resources", "search_vector")

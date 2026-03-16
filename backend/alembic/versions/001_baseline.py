"""Baseline migration — marks the initial schema as the starting point for Alembic.

The pharmacy database schema was originally created via SQLAlchemy's
create_all() and a series of ad-hoc Python/SQL migration scripts. This
revision represents that baseline state so Alembic can track all future
changes from a known version.

To apply this baseline to an existing database (without re-running DDL):
    alembic stamp 001_baseline

For a brand-new database, run:
    alembic upgrade head

Revision ID: 001_baseline
Revises:
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This migration is intentionally empty — it marks the existing schema
    # (created by create_all + manual migration scripts) as the Alembic baseline.
    # All subsequent revisions will apply incremental DDL changes.
    pass


def downgrade() -> None:
    # Downgrading the baseline is a no-op. To fully remove the schema,
    # drop the database directly.
    pass

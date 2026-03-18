"""Add unique constraint on prescribers.npi.

NPIs (National Provider Identifiers) are federally assigned and globally unique.
The application queries prescribers by NPI assuming at most one result
(refills.py — .first() call). Without a DB-level constraint a duplicate NPI
can be inserted and the query silently returns the wrong prescriber.

This migration adds a unique index on prescribers.npi and drops the plain
non-unique index that was previously created by SQLAlchemy's index=True.

Revision ID: 003_add_npi_unique_constraint
Revises: 002_perf_indexes
Create Date: 2026-03-18
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "003_add_npi_unique_constraint"
down_revision = "002_perf_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the plain index if it was previously created (safe if absent).
    op.drop_index("ix_prescribers_npi", table_name="prescribers", if_exists=True)

    # Add the unique constraint (also serves as the lookup index).
    op.create_index(
        "ix_prescribers_npi",
        "prescribers",
        ["npi"],
        unique=True,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_prescribers_npi", table_name="prescribers", if_exists=True)

    # Restore a plain (non-unique) index.
    op.create_index(
        "ix_prescribers_npi",
        "prescribers",
        ["npi"],
        unique=False,
        if_not_exists=True,
    )

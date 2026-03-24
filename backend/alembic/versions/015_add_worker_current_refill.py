"""Add current_refill_id to sim_workers table.

Adds a nullable FK column so each SimWorker can record which refill they are
currently processing. The task layer sets this to the last refill in the
worker's batch and clears it when the worker travels between stations or has
nothing to process.  This powers the "currently working on" display in the
Worker Dashboard.

Revision ID: 015
Revises: 014_add_drug_form
"""

from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sim_workers",
        sa.Column("current_refill_id", sa.Integer(), sa.ForeignKey("refills.id"), nullable=True),
        schema=None,
    )
    op.create_index(
        "ix_sim_workers_current_refill_id",
        "sim_workers",
        ["current_refill_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_sim_workers_current_refill_id", table_name="sim_workers")
    op.drop_column("sim_workers", "current_refill_id")

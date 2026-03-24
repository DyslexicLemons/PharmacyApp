"""Add task_started_at to sim_workers table.

Records the moment a worker began traveling between stations. Combined with
busy_until this lets the frontend compute travel progress as a percentage,
enabling a smooth progress bar instead of just a raw countdown.

Revision ID: 016
Revises: 015
"""

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sim_workers",
        sa.Column("task_started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sim_workers", "task_started_at")

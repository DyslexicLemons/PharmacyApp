"""Add system_config table for pharmacy-wide settings.

Introduces a singleton configuration table (always id=1) that persists
admin-adjustable settings across restarts. Initial setting: bin_count (default 100),
which controls the number of ready-shelf bins used during refill bin assignment.

Revision ID: 005_add_system_config
Revises: 004_drop_picture_column
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "005_add_system_config"
down_revision = "004_drop_picture_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bin_count", sa.Integer(), nullable=False, server_default="100"),
        if_not_exists=True,
    )
    # Insert the singleton row if it doesn't exist yet
    op.execute(
        "INSERT INTO system_config (id, bin_count) VALUES (1, 100) "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("system_config", if_exists=True)

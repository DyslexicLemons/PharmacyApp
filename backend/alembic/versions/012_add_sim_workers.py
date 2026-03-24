"""Add sim_workers table for configurable virtual pharmacy workers.

Each row represents a virtual technician or pharmacist used by the simulation
Celery tasks. The speed column (1–10) controls how many refills that worker
processes per cycle; is_active lets admins bench workers without deleting them.

Revision ID: 012
Revises: 011
Create Date: 2026-03-21
"""

from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sim_workers",
        sa.Column("id", sa.Integer(), primary_key=True, index=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("technician", "pharmacist", name="simworkerrole"),
            nullable=False,
            index=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("speed", sa.Integer(), nullable=False, server_default="5"),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("sim_workers", if_exists=True)
    op.execute("DROP TYPE IF EXISTS simworkerrole")

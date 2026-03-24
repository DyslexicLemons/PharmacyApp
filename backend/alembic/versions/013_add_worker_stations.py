"""Add station tracking to sim_workers.

Each SimWorker now has a current_station (where they are in the pharmacy) and
busy_until (when they finish traveling and become available). Moving between
stations takes 5–10 seconds of simulated travel time.

Revision ID: 013
Revises: 012
Create Date: 2026-03-21
"""

from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    stationname = sa.Enum(
        "triage", "fill", "verify_1", "verify_2", "window",
        name="stationname",
    )
    stationname.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "sim_workers",
        sa.Column("current_station", stationname, nullable=True),
    )
    op.add_column(
        "sim_workers",
        sa.Column("busy_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sim_workers", "busy_until")
    op.drop_column("sim_workers", "current_station")
    op.execute("DROP TYPE IF EXISTS stationname")

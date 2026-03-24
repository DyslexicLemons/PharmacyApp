"""Add simulation configuration columns to system_config.

Extends the singleton system_config table with three new columns that control
the virtual pharmacy simulation engine:
  - simulation_enabled: master on/off switch for all sim Celery tasks
  - sim_arrival_rate:   max new prescriptions created per arrival cycle (1–10)
  - sim_reject_rate:    % probability a virtual pharmacist rejects at QV1 (0–50)

Revision ID: 010_add_simulation_config
Revises: d1e8d85f752f
Create Date: 2026-03-21
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "010_add_simulation_config"
down_revision = "d1e8d85f752f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_config",
        sa.Column(
            "simulation_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "system_config",
        sa.Column(
            "sim_arrival_rate",
            sa.Integer(),
            nullable=False,
            server_default="2",
        ),
    )
    op.add_column(
        "system_config",
        sa.Column(
            "sim_reject_rate",
            sa.Integer(),
            nullable=False,
            server_default="10",
        ),
    )


def downgrade() -> None:
    op.drop_column("system_config", "sim_reject_rate")
    op.drop_column("system_config", "sim_arrival_rate")
    op.drop_column("system_config", "simulation_enabled")

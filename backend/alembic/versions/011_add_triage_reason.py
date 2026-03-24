"""Add triage_reason column to refills table.

Stores the reason a refill was routed to the QT (triage) queue so staff can
see why a script needs review rather than having to infer it from logs.

Revision ID: 011
Revises: 010_add_simulation_config
Create Date: 2026-03-21
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "011"
down_revision = "010_add_simulation_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "refills",
        sa.Column("triage_reason", sa.String(), nullable=True),
        schema=None,
    )


def downgrade() -> None:
    op.drop_column("refills", "triage_reason")

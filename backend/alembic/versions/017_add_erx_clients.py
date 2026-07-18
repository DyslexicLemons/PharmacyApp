"""Add erx_clients table for external e-prescribing OAuth clients.

Introduces the erx_clients table, which holds OAuth2 client-credentials
for external medical clinics that submit prescriptions via the
POST /eprescribe/newrx intake API. Each row is a clinic's registered
API client: a public client_id, a bcrypt-hashed client_secret, and
basic clinic contact metadata. Clients are soft-deactivated (is_active)
rather than deleted so historical audit trail (erx-attributed
prescriptions/refills) stays attributable to a real clinic record.

Revision ID: 017_add_erx_clients
Revises: 72bbf0fcbd07
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "017_add_erx_clients"
down_revision = "72bbf0fcbd07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erx_clients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("hashed_client_secret", sa.String(), nullable=False),
        sa.Column("clinic_name", sa.String(), nullable=False),
        sa.Column("contact_email", sa.String(), nullable=True),
        sa.Column("contact_phone", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id"),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("erx_clients", if_exists=True)

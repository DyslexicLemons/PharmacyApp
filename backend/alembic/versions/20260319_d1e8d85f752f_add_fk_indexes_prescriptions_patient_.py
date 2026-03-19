"""Add missing FK indexes on prescriptions.patient_id and refills.prescription_id.

Both columns are high-frequency join targets but were missing index=True on the
model and had no explicit migration. Without these indexes, queries like
"load all prescriptions for a patient" or "load all refills for a prescription"
require a sequential scan on those tables.

Revision ID: d1e8d85f752f
Revises: 009_add_user_role
Create Date: 2026-03-19
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'd1e8d85f752f'
down_revision = '009_add_user_role'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        op.f('ix_prescriptions_patient_id'),
        'prescriptions',
        ['patient_id'],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f('ix_refills_prescription_id'),
        'refills',
        ['prescription_id'],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_refills_prescription_id'), table_name='refills', if_exists=True)
    op.drop_index(op.f('ix_prescriptions_patient_id'), table_name='prescriptions', if_exists=True)

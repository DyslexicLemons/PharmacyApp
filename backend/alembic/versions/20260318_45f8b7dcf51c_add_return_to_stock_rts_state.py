"""Add return_to_stock table and RTS state to rxstate enum.

Creates the return_to_stock table to track all prescriptions returned from
the READY bin back to inventory, and adds the RTS terminal state to the
rxstate PostgreSQL enum.

Revision ID: 45f8b7dcf51c
Revises: 005_add_system_config
Create Date: 2026-03-18 23:41:18.351342
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '45f8b7dcf51c'
down_revision = '005_add_system_config'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add RTS to the rxstate enum (IF NOT EXISTS is safe to re-run).
    # Cannot be done inside a transaction on older PG versions, but PG 12+ handles it fine.
    op.execute("ALTER TYPE rxstate ADD VALUE IF NOT EXISTS 'RTS'")

    # Create the return_to_stock table
    op.create_table(
        'return_to_stock',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('refill_id', sa.Integer(), nullable=False),
        sa.Column('drug_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('returned_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('returned_by', sa.String(), nullable=False),
        sa.Column('returned_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['drug_id'], ['drugs.id']),
        sa.ForeignKeyConstraint(['refill_id'], ['refills.id']),
        sa.ForeignKeyConstraint(['returned_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True,
    )
    op.create_index(op.f('ix_return_to_stock_drug_id'), 'return_to_stock', ['drug_id'], unique=False)
    op.create_index(op.f('ix_return_to_stock_id'), 'return_to_stock', ['id'], unique=False)
    op.create_index(op.f('ix_return_to_stock_refill_id'), 'return_to_stock', ['refill_id'], unique=False)
    op.create_index(op.f('ix_return_to_stock_returned_at'), 'return_to_stock', ['returned_at'], unique=False)

    # Schema drift fixes detected by autogenerate (pre-existing model/DB mismatches)
    op.drop_constraint(op.f('audit_log_user_id_fkey'), 'audit_log', type_='foreignkey')
    op.create_foreign_key(None, 'audit_log', 'users', ['user_id'], ['id'])
    op.alter_column('prescriptions', 'instructions', existing_type=sa.VARCHAR(), nullable=True)
    op.alter_column('prescriptions', 'picture_path',
                    existing_type=sa.TEXT(), type_=sa.String(), existing_nullable=True)
    op.drop_column('prescriptions', 'brand_required')
    op.alter_column('quick_codes', 'code',
                    existing_type=sa.VARCHAR(length=3), type_=sa.String(length=6), existing_nullable=False)
    op.create_index(op.f('ix_refills_patient_id'), 'refills', ['patient_id'], unique=False)
    op.alter_column('users', 'is_admin',
                    existing_type=sa.BOOLEAN(), nullable=True,
                    existing_server_default=sa.text('false'))


def downgrade() -> None:
    # NOTE: PostgreSQL does not support removing enum values.
    # The 'RTS' value added to rxstate cannot be rolled back automatically.

    # Reverse schema drift fixes
    op.alter_column('users', 'is_admin',
                    existing_type=sa.BOOLEAN(), nullable=False,
                    existing_server_default=sa.text('false'))
    op.drop_index(op.f('ix_refills_patient_id'), table_name='refills')
    op.alter_column('quick_codes', 'code',
                    existing_type=sa.String(length=6), type_=sa.VARCHAR(length=3), existing_nullable=False)
    op.add_column('prescriptions', sa.Column('brand_required', sa.BOOLEAN(), autoincrement=False, nullable=True))
    op.alter_column('prescriptions', 'picture_path',
                    existing_type=sa.String(), type_=sa.TEXT(), existing_nullable=True)
    op.alter_column('prescriptions', 'instructions', existing_type=sa.VARCHAR(), nullable=False)
    op.drop_constraint(None, 'audit_log', type_='foreignkey')
    op.create_foreign_key(
        op.f('audit_log_user_id_fkey'), 'audit_log', 'users', ['user_id'], ['id'], ondelete='SET NULL'
    )

    # Drop the return_to_stock table
    op.drop_index(op.f('ix_return_to_stock_returned_at'), table_name='return_to_stock')
    op.drop_index(op.f('ix_return_to_stock_refill_id'), table_name='return_to_stock')
    op.drop_index(op.f('ix_return_to_stock_id'), table_name='return_to_stock')
    op.drop_index(op.f('ix_return_to_stock_drug_id'), table_name='return_to_stock')
    op.drop_table('return_to_stock', if_exists=True)

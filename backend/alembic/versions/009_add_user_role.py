"""Add `role` column to users table.

Introduces a three-value role system: 'admin', 'pharmacist', 'technician'.
This enables per-step actor constraints on the refill state machine — QV1 and
QV2 verifications are legally required to be performed by a licensed pharmacist
(RPh) and are now gated in the API accordingly.

Back-fill strategy for existing rows:
  - Users with is_admin = true  → role = 'admin'
  - All other existing users    → role = 'pharmacist'  (preserves prior behaviour)
New users created via the API default to 'technician' (safe default).

Revision ID: 009_add_user_role
Revises: 008_merge_heads
Create Date: 2026-03-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "009_add_user_role"
down_revision = "008_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Check whether the column already exists (guard against manual migrate_add_role.py runs).
    inspector = sa.inspect(conn)
    existing_cols = [c["name"] for c in inspector.get_columns("users")]
    if "role" not in existing_cols:
        op.add_column("users", sa.Column("role", sa.String(), nullable=False, server_default="technician"))

    # Back-fill: admins → 'admin', everyone else → 'pharmacist' to preserve old behaviour.
    conn.execute(text("UPDATE users SET role = 'admin' WHERE is_admin = true AND role = 'technician'"))
    conn.execute(text("UPDATE users SET role = 'pharmacist' WHERE is_admin = false AND role = 'technician'"))


def downgrade() -> None:
    op.drop_column("users", "role")

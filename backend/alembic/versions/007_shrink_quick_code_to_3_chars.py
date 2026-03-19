"""Shrink quick_codes.code column from VARCHAR(6) back to VARCHAR(3).

The code length was mistakenly expanded to 6 in a prior migration but the
application has always generated 3-character codes (_QUICK_CODE_LENGTH = 3).
This aligns the DB constraint with the actual behaviour.

Revision ID: 007_shrink_quick_code_to_3_chars
Revises: 006_audit_log_immutable_trigger
Create Date: 2026-03-19
"""

import sqlalchemy as sa
from alembic import op

revision = "007_shrink_quick_code_to_3_chars"
down_revision = "006_audit_log_immutable_trigger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "quick_codes",
        "code",
        type_=sa.String(3),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "quick_codes",
        "code",
        type_=sa.String(6),
        existing_nullable=False,
    )

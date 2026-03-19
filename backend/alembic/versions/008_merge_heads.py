"""Merge 45f8b7dcf51c (RTS) and 007_shrink_quick_code_to_3_chars into a single head.

Revision ID: 008_merge_heads
Revises: 45f8b7dcf51c, 007_shrink_quick_code_to_3_chars
Create Date: 2026-03-19
"""

from alembic import op

revision = "008_merge_heads"
down_revision = ("45f8b7dcf51c", "007_shrink_quick_code_to_3_chars")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

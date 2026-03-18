"""Drop prescriptions.picture column (legacy base64 PHI storage).

The picture column stored base64-encoded prescription images directly in the
primary database with no separate access controls. All image storage has been
migrated to the filesystem via picture_path. The column was confirmed empty
before this migration was applied.

Revision ID: 004_drop_picture_column
Revises: 003_add_npi_unique_constraint
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "004_drop_picture_column"
down_revision = "003_add_npi_unique_constraint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("prescriptions", "picture")


def downgrade() -> None:
    op.add_column(
        "prescriptions",
        sa.Column("picture", sa.String(), nullable=True),
    )

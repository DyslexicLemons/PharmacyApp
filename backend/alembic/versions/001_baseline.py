"""Baseline migration — creates the initial schema for a fresh database.

All tables reflect the schema as it existed before any incremental migration
ran.  Columns that are dropped or altered in later migrations are included here
in their original form so the full migration chain can be replayed cleanly from
an empty database with `alembic upgrade head`.

Notable baseline quirks (corrected by later migrations):
  - prescriptions.instructions  — NOT NULL (made nullable in 45f8b7dcf51c)
  - prescriptions.picture_path  — TEXT     (changed to VARCHAR in 45f8b7dcf51c)
  - prescriptions.picture       — present  (dropped in 004_drop_picture_column)
  - prescriptions.brand_required — present (dropped in 45f8b7dcf51c)
  - quick_codes.code            — VARCHAR(3) (expanded to 6 in 45f8b7dcf51c, shrunk back in 007)
  - users.is_admin              — NOT NULL  (made nullable in 45f8b7dcf51c)
  - audit_log.user_id FK        — ON DELETE SET NULL (recreated without ondelete in 45f8b7dcf51c)
  - rxstate enum                — no 'RTS' value (added in 45f8b7dcf51c)
  - system_config table         — absent (created in 005_add_system_config)
  - return_to_stock table       — absent (created in 45f8b7dcf51c)

To apply this baseline to an existing database (without re-running DDL):
    alembic stamp 001_baseline

For a brand-new database, run:
    alembic upgrade head

Revision ID: 001_baseline
Revises:
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

# revision identifiers, used by Alembic.
revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── PostgreSQL enum types ────────────────────────────────────────────────
    # PostgreSQL has no CREATE TYPE IF NOT EXISTS, so use a DO block to guard.
    # 'RTS' is intentionally absent from rxstate — added by 45f8b7dcf51c.
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'rxstate') THEN
                CREATE TYPE rxstate AS ENUM
                    ('QT', 'QV1', 'QP', 'QV2', 'READY', 'HOLD', 'SCHEDULED', 'REJECTED', 'SOLD');
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'priority') THEN
                CREATE TYPE priority AS ENUM ('Low', 'Normal', 'High', 'Stat');
            END IF;
        END $$;
    """)

    # ── Leaf tables (no FK dependencies) ────────────────────────────────────

    op.create_table(
        "patients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("dob", sa.Date(), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("state", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )

    op.create_table(
        "prescribers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("npi", sa.BigInteger(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("phone_number", sa.String(), nullable=True),
        sa.Column("specialty", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )

    op.create_table(
        "drugs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("drug_name", sa.String(), nullable=True),
        sa.Column("ndc", sa.String(), nullable=True),
        sa.Column("manufacturer", sa.String(), nullable=True),
        sa.Column("cost", sa.Numeric(10, 2), nullable=False),
        sa.Column("niosh", sa.Boolean(), nullable=True),
        sa.Column("drug_class", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        # drug_form column is absent at baseline — added in 014_add_drug_form
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )

    op.create_table(
        "insurance_companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.String(), nullable=True),
        sa.Column("plan_name", sa.String(), nullable=True),
        sa.Column("bin_number", sa.String(), nullable=True),
        sa.Column("pcn", sa.String(), nullable=True),
        sa.Column("phone_number", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id"),
        if_not_exists=True,
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        # is_admin is NOT NULL at baseline (made nullable in 45f8b7dcf51c)
        # role column absent at baseline — added in 009_add_user_role
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        if_not_exists=True,
    )

    # ── Tables with one level of FK dependencies ─────────────────────────────

    op.create_table(
        "stock",
        sa.Column("drug_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("package_size", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["drug_id"], ["drugs.id"]),
        sa.PrimaryKeyConstraint("drug_id"),
        if_not_exists=True,
    )

    op.create_table(
        "formulary",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("insurance_company_id", sa.Integer(), nullable=True),
        sa.Column("drug_id", sa.Integer(), nullable=True),
        sa.Column("tier", sa.Integer(), nullable=True),
        sa.Column("copay_per_30", sa.Numeric(10, 2), nullable=True),
        sa.Column("not_covered", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["drug_id"], ["drugs.id"]),
        sa.ForeignKeyConstraint(["insurance_company_id"], ["insurance_companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )

    op.create_table(
        "patient_insurance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=True),
        sa.Column("insurance_company_id", sa.Integer(), nullable=True),
        sa.Column("member_id", sa.String(), nullable=True),
        sa.Column("group_number", sa.String(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["insurance_company_id"], ["insurance_companies.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )

    op.create_table(
        "quick_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        # VARCHAR(3) at baseline; expanded to 6 in 45f8b7dcf51c, shrunk back in 007
        sa.Column("code", sa.String(3), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )

    op.create_table(
        "inventory_shipments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("performed_by", sa.String(), nullable=False),
        sa.Column("performed_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["performed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )

    # ── Tables with two levels of FK dependencies ────────────────────────────

    op.create_table(
        "prescriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("drug_id", sa.Integer(), nullable=True),
        sa.Column("daw_code", sa.Integer(), nullable=True),
        sa.Column("original_quantity", sa.Integer(), nullable=True),
        sa.Column("remaining_quantity", sa.Integer(), nullable=True),
        sa.Column("date_received", sa.Date(), nullable=True),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        # NOT NULL at baseline; made nullable in 45f8b7dcf51c
        sa.Column("instructions", sa.String(), nullable=False),
        # Present at baseline; dropped in 004_drop_picture_column
        sa.Column("picture", sa.String(), nullable=True),
        # TEXT at baseline; changed to VARCHAR in 45f8b7dcf51c
        sa.Column("picture_path", sa.Text(), nullable=True),
        # Present at baseline; dropped in 45f8b7dcf51c
        sa.Column("brand_required", sa.Boolean(), nullable=True),
        sa.Column("is_inactive", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("patient_id", sa.Integer(), nullable=True),
        sa.Column("prescriber_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["drug_id"], ["drugs.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["prescriber_id"], ["prescribers.id"]),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )

    op.create_table(
        "inventory_shipment_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column("drug_id", sa.Integer(), nullable=False),
        sa.Column("bottles_received", sa.Integer(), nullable=False),
        sa.Column("units_per_bottle", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["drug_id"], ["drugs.id"]),
        sa.ForeignKeyConstraint(["shipment_id"], ["inventory_shipments.id"]),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )

    # ── Tables that depend on prescriptions / patient_insurance ──────────────

    op.create_table(
        "refills",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prescription_id", sa.Integer(), nullable=True),
        sa.Column("patient_id", sa.Integer(), nullable=True),
        sa.Column("drug_id", sa.Integer(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("days_supply", sa.Integer(), nullable=True),
        sa.Column("total_cost", sa.Numeric(10, 2), nullable=False),
        sa.Column("priority", PgEnum(name="priority", create_type=False), nullable=True),
        sa.Column("state", PgEnum(name="rxstate", create_type=False), nullable=True),
        sa.Column("completed_date", sa.Date(), nullable=True),
        sa.Column("bin_number", sa.Integer(), nullable=True),
        sa.Column("rejected_by", sa.String(), nullable=True),
        sa.Column("rejection_reason", sa.String(), nullable=True),
        sa.Column("rejection_date", sa.Date(), nullable=True),
        # triage_reason column absent at baseline — added in 011_add_triage_reason
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("insurance_id", sa.Integer(), nullable=True),
        sa.Column("copay_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("insurance_paid", sa.Numeric(10, 2), nullable=True),
        sa.ForeignKeyConstraint(["drug_id"], ["drugs.id"]),
        sa.ForeignKeyConstraint(["insurance_id"], ["patient_insurance.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["prescription_id"], ["prescriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )

    op.create_table(
        "refill_hist",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prescription_id", sa.Integer(), nullable=True),
        sa.Column("patient_id", sa.Integer(), nullable=True),
        sa.Column("drug_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("days_supply", sa.Integer(), nullable=True),
        sa.Column("completed_date", sa.Date(), nullable=True),
        sa.Column("sold_date", sa.Date(), nullable=True),
        sa.Column("total_cost", sa.Numeric(10, 2), nullable=False),
        sa.Column("insurance_id", sa.Integer(), nullable=True),
        sa.Column("copay_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("insurance_paid", sa.Numeric(10, 2), nullable=True),
        sa.ForeignKeyConstraint(["drug_id"], ["drugs.id"]),
        sa.ForeignKeyConstraint(["insurance_id"], ["patient_insurance.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["prescription_id"], ["prescriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )

    # ── audit_log — user_id FK uses ON DELETE SET NULL at baseline ───────────
    # 45f8b7dcf51c drops and recreates this FK without ondelete.
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.String(), nullable=True),
        sa.Column("prescription_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("performed_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("audit_log", if_exists=True)
    op.drop_table("refill_hist", if_exists=True)
    op.drop_table("refills", if_exists=True)
    op.drop_table("inventory_shipment_items", if_exists=True)
    op.drop_table("prescriptions", if_exists=True)
    op.drop_table("quick_codes", if_exists=True)
    op.drop_table("inventory_shipments", if_exists=True)
    op.drop_table("patient_insurance", if_exists=True)
    op.drop_table("formulary", if_exists=True)
    op.drop_table("stock", if_exists=True)
    op.drop_table("users", if_exists=True)
    op.drop_table("insurance_companies", if_exists=True)
    op.drop_table("drugs", if_exists=True)
    op.drop_table("prescribers", if_exists=True)
    op.drop_table("patients", if_exists=True)

    bind = op.get_bind()
    sa.Enum(name="priority").drop(bind, checkfirst=True)
    sa.Enum(name="rxstate").drop(bind, checkfirst=True)

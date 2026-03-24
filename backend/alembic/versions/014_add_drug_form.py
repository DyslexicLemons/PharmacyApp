"""Add drug_form column to drugs table.

Adds a DrugForm enum column to the drugs table so the system knows the
physical/delivery form of each drug (Tablet, Capsule, Injection, etc.).
This drives SIG code translation defaults — e.g., "QD" on a Tablet drug
expands to "Take 1 tablet by mouth once daily", whereas the same code on
a Liquid drug yields "Take ___ mL by mouth once daily".

The column is nullable with a server-default of 'Unknown' so existing rows
remain valid.  A data migration below sets the correct form for all 100
seeded drugs using description-pattern matching.

Revision ID: 014
Revises: 013_add_worker_stations
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create the PostgreSQL enum type
    drug_form_enum = postgresql.ENUM(
        "Tablet", "Capsule", "Liquid", "Injection", "Patch",
        "Film", "Topical", "Inhaler", "Drops", "Suppository", "Powder", "Unknown",
        name="drugform",
    )
    drug_form_enum.create(op.get_bind(), checkfirst=True)

    # 2. Add the column (nullable, server default 'Unknown')
    op.add_column(
        "drugs",
        sa.Column(
            "drug_form",
            sa.Enum(
                "Tablet", "Capsule", "Liquid", "Injection", "Patch",
                "Film", "Topical", "Inhaler", "Drops", "Suppository", "Powder", "Unknown",
                name="drugform",
                create_type=False,  # already created above
            ),
            nullable=True,
            server_default="Unknown",
        ),
    )

    # 3. Data migration: set drug_form based on description/name patterns for
    #    existing seeded rows.  Order matters — more specific patterns first.
    conn = op.get_bind()

    # Explicit per-name overrides for drugs whose form isn't obvious from
    # the description alone (pen injectors, films, patches, etc.)
    explicit: list[tuple[str, str]] = [
        ("Buprenorphine 8mg",              "Film"),
        ("Fentanyl 50mcg/hr patch",        "Patch"),
        ("Dulaglutide 1.5mg/0.5mL",        "Injection"),
        ("Semaglutide 1mg/0.5mL",          "Injection"),
        ("Naloxone 0.4mg/mL",              "Injection"),
        ("Carboplatin 50mg/5mL",           "Injection"),
        ("Paclitaxel 30mg/5mL",            "Injection"),
        ("Docetaxel 20mg/0.5mL",           "Injection"),
        ("Fluorouracil 500mg/10mL",        "Injection"),
        ("Gemcitabine 200mg",              "Injection"),
        ("Oxaliplatin 50mg",               "Injection"),
    ]
    for name, form in explicit:
        conn.execute(
            sa.text(
                "UPDATE drugs SET drug_form = CAST(:form AS drugform) "
                "WHERE drug_name = :name AND drug_form IS NULL"
            ),
            {"form": form, "name": name},
        )

    # Description-based pattern rules (applied after explicit overrides)
    pattern_rules: list[tuple[str, str]] = [
        ("%capsule%",    "Capsule"),
        ("%vial%",       "Injection"),
        ("%solution%",   "Injection"),
        ("%powder%",     "Injection"),   # lyophilised powder for injection
        ("%patch%",      "Patch"),
        ("%film%",       "Film"),
        ("%cream%",      "Topical"),
        ("%ointment%",   "Topical"),
        ("%gel%",        "Topical"),
        ("%inhaler%",    "Inhaler"),
        ("%drops%",      "Drops"),
        ("%suppository%","Suppository"),
        ("%tablet%",     "Tablet"),
        ("%caplet%",     "Tablet"),
    ]
    for pattern, form in pattern_rules:
        conn.execute(
            sa.text(
                "UPDATE drugs SET drug_form = CAST(:form AS drugform) "
                "WHERE drug_form IS NULL AND LOWER(description) LIKE :pat"
            ),
            {"form": form, "pat": pattern},
        )

    # Anything still NULL → Unknown
    conn.execute(
        sa.text(
            "UPDATE drugs SET drug_form = 'Unknown' WHERE drug_form IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_column("drugs", "drug_form")
    # Remove the PostgreSQL enum type only if no other tables use it
    drug_form_enum = postgresql.ENUM(name="drugform")
    drug_form_enum.drop(op.get_bind(), checkfirst=True)

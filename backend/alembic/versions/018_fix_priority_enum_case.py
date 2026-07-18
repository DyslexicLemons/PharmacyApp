"""Fix priority enum label casing drift (low/normal/high/stat -> Low/Normal/High/Stat).

The Refill.priority column (models.py) is declared with
values_callable=lambda x: [e.value for e in x], so SQLAlchemy reads/writes
the Priority enum's *values* ("Low", "Normal", "High", "Stat"), and
001_baseline.py's CREATE TYPE statement matches that casing. But baseline
was authored to be applied via `alembic stamp` on already-existing
databases (see its docstring) rather than re-run as DDL, so any database
whose priority type predates the baseline squash can still carry the
type's original lowercase labels ("low", "normal", "high", "stat").

On such a database every new refill INSERT fails with
"invalid input value for enum priority" (SQLAlchemy sends the capitalized
value, Postgres only recognizes lowercase), and every SELECT of an
existing row fails with a LookupError (Postgres returns lowercase,
SQLAlchemy can't map it back to a Priority member). This affects any
endpoint that creates/reads a Refill — discovered via /refills/upload_json
and the new /eprescribe/newrx endpoint, but present before either existed.

RENAME VALUE only relabels the enum (same underlying OID), so existing
rows keep referring to the same value — no data/UPDATE migration needed.
Both directions are idempotent: guarded by checking pg_enum first, so this
is a no-op on a database that already has the correct (or already-reverted)
casing, e.g. a fresh test DB built from models.py via create_all().

Revision ID: 018_fix_priority_enum_case
Revises: 017_add_erx_clients
Create Date: 2026-07-18
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "018_fix_priority_enum_case"
down_revision = "017_add_erx_clients"
branch_labels = None
depends_on = None

_LOWER_TO_UPPER = [
    ("low", "Low"),
    ("normal", "Normal"),
    ("high", "High"),
    ("stat", "Stat"),
]


def _rename_if_present(from_label: str, to_label: str) -> None:
    op.execute(f"""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumtypid = 'priority'::regtype AND enumlabel = '{from_label}'
            ) THEN
                ALTER TYPE priority RENAME VALUE '{from_label}' TO '{to_label}';
            END IF;
        END $$;
    """)


def upgrade() -> None:
    for lower, upper in _LOWER_TO_UPPER:
        _rename_if_present(lower, upper)


def downgrade() -> None:
    for lower, upper in _LOWER_TO_UPPER:
        _rename_if_present(upper, lower)

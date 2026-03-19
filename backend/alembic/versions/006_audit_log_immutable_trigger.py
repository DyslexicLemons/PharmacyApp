"""Make audit_log append-only via a database trigger.

Adds a BEFORE DELETE OR UPDATE trigger on audit_log that raises an exception
for any attempt to modify or remove a row. Prevents accidental (and casual
intentional) tampering with the audit trail. Does not protect against a
superuser who can DROP the trigger directly.

Revision ID: 006_audit_log_immutable_trigger
Revises: 005_add_system_config
Create Date: 2026-03-19
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "006_audit_log_immutable_trigger"
down_revision = "005_add_system_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_log_immutable()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only: DELETE and UPDATE are not permitted';
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_audit_log_immutable
        BEFORE DELETE OR UPDATE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS audit_log_immutable();")

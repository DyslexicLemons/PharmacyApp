"""
Migration: Add prescription_id column to the audit_log table.

Usage:
    cd backend
    python -m app.migrate_add_prescription_id_to_audit

Safe to run multiple times — checks for column existence before adding.
"""

from sqlalchemy import text
from .database import engine


def run():
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'audit_log'"
        ))
        existing_columns = {row[0] for row in result}

        if "prescription_id" not in existing_columns:
            conn.execute(text(
                "ALTER TABLE audit_log ADD COLUMN prescription_id INTEGER"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_audit_log_prescription_id "
                "ON audit_log(prescription_id)"
            ))
            print("Added column: audit_log.prescription_id")
        else:
            print("Column audit_log.prescription_id already exists — skipping.")

        conn.commit()
        print("Migration complete.")


if __name__ == "__main__":
    run()

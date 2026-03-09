"""
Migration: Add user_id and performed_by columns to the audit_log table.

Usage:
    cd backend
    python -m app.migrate_add_audit_user

Safe to run multiple times — checks for column existence before adding.
"""

from sqlalchemy import text
from .database import engine


def run():
    with engine.connect() as conn:
        # Check existing columns
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'audit_log'"
        ))
        existing_columns = {row[0] for row in result}

        if "user_id" not in existing_columns:
            conn.execute(text(
                "ALTER TABLE audit_log "
                "ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
            ))
            print("Added column: audit_log.user_id")
        else:
            print("Column audit_log.user_id already exists — skipping.")

        if "performed_by" not in existing_columns:
            conn.execute(text(
                "ALTER TABLE audit_log ADD COLUMN performed_by VARCHAR"
            ))
            print("Added column: audit_log.performed_by")
        else:
            print("Column audit_log.performed_by already exists — skipping.")

        # Index user_id for fast filtering by user
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_audit_log_user_id ON audit_log(user_id)"
        ))
        conn.commit()
        print("Migration complete.")


if __name__ == "__main__":
    run()

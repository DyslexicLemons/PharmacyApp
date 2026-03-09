"""
Migration: add is_inactive column to prescriptions table.

Run once:
    cd backend
    python -m app.migrate_add_is_inactive
"""
from sqlalchemy import text
from .database import engine


def run():
    with engine.connect() as conn:
        existing_cols = {
            row[0]
            for row in conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='prescriptions'")
            )
        }

        if "is_inactive" not in existing_cols:
            conn.execute(text("ALTER TABLE prescriptions ADD COLUMN is_inactive BOOLEAN NOT NULL DEFAULT FALSE"))
            conn.commit()
            print("Added column: is_inactive")
        else:
            print("Column is_inactive already exists, skipping.")


if __name__ == "__main__":
    run()

"""
Migration: add expiration_date column to prescriptions table.

Run once:
    cd backend
    python -m app.migrate_add_expiration_date
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

        if "expiration_date" not in existing_cols:
            conn.execute(text("ALTER TABLE prescriptions ADD COLUMN expiration_date DATE"))
            conn.commit()
            print("Added column: expiration_date")
        else:
            print("Column expiration_date already exists, skipping.")


if __name__ == "__main__":
    run()

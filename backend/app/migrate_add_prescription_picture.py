"""
Migration: add picture column to prescriptions table.

Run once:
    cd backend
    python -m app.migrate_add_prescription_picture
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

        if "picture" not in existing_cols:
            conn.execute(text("ALTER TABLE prescriptions ADD COLUMN picture TEXT"))
            conn.commit()
            print("Added column: picture")
        else:
            print("Column picture already exists, skipping.")

        if "picture_path" not in existing_cols:
            conn.execute(text("ALTER TABLE prescriptions ADD COLUMN picture_path TEXT"))
            conn.commit()
            print("Added column: picture_path")
        else:
            print("Column picture_path already exists, skipping.")


if __name__ == "__main__":
    run()

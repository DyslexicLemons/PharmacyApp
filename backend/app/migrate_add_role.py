"""
Migration: add `role` column to the users table.

Existing users are assigned:
  - "admin" if is_admin = true
  - "pharmacist" otherwise

Run once:
    python -m app.migrate_add_role
"""

from .database import engine
from sqlalchemy import text


def run():
    with engine.begin() as conn:
        # Add column (nullable so existing rows don't violate NOT NULL)
        try:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'pharmacist'"
            ))
            print("Added 'role' column.")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("Column 'role' already exists — skipping ALTER TABLE.")
            else:
                raise

        # Back-fill: admins → "admin", everyone else stays "pharmacist"
        conn.execute(text(
            "UPDATE users SET role = 'admin' WHERE is_admin = 1 OR is_admin = true"
        ))
        print("Back-filled role for existing users.")


if __name__ == "__main__":
    run()

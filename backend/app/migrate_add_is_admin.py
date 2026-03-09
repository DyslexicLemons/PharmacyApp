"""
Migration: Add is_admin column to users table and mark default admin user.

Usage:
    cd backend
    python -m app.migrate_add_is_admin
"""

from .database import engine
from sqlalchemy import text


def run():
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE"))
            conn.execute(text("UPDATE users SET is_admin = TRUE WHERE username = 'admin'"))
            conn.commit()
            print("Migration complete: added is_admin column and marked 'admin' as admin.")
        except Exception as e:
            # Column likely already exists
            print(f"Migration skipped (may already be applied): {e}")


if __name__ == "__main__":
    run()

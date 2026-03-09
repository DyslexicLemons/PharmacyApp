"""Migration: create quick_codes table for short-lived 3-letter login codes."""
from .database import engine
from sqlalchemy import text

def run():
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS quick_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id),
                expires_at DATETIME NOT NULL,
                used INTEGER NOT NULL DEFAULT 0
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_quick_codes_code ON quick_codes (code)"))
        conn.commit()
    print("Migration complete: quick_codes table ready.")

if __name__ == "__main__":
    run()

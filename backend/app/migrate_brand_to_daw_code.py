"""Migration: replace brand_required (Boolean) with daw_code (Integer 0-9).

brand_required=True  → daw_code=1 (Substitution not allowed by prescriber)
brand_required=False → daw_code=0 (No product selection indicated / generic OK)
"""

from .database import SessionLocal
from sqlalchemy import text


def run():
    db = SessionLocal()
    try:
        # Add daw_code column if it doesn't already exist
        db.execute(text("""
            ALTER TABLE prescriptions ADD COLUMN IF NOT EXISTS daw_code INTEGER
        """))
        db.commit()

        # Migrate existing data
        db.execute(text("""
            UPDATE prescriptions
            SET daw_code = CASE WHEN brand_required = TRUE THEN 1 ELSE 0 END
            WHERE daw_code IS NULL
        """))
        db.commit()

        # Drop old column (SQLite requires recreate — skip for simplicity; column stays dormant)
        # For PostgreSQL you could run: ALTER TABLE prescriptions DROP COLUMN brand_required;
        print("Migration complete: daw_code column added and populated.")
    except Exception as e:
        db.rollback()
        print(f"Migration error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    run()

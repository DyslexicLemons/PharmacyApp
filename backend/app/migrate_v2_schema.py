"""
Migration: v2 schema changes
Adds picture_path to prescriptions, expands quick_codes.code to VARCHAR(6),
and adds an index on refills.patient_id.

Run ONCE before deploying the new backend code:
    cd backend
    python -m app.migrate_v2_schema
"""

import os
import sys

# Require DATABASE_URL to be set
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable is required.")
    print("Example: DATABASE_URL=postgresql://postgres:password@localhost/pharmacy_db python -m app.migrate_v2_schema")
    sys.exit(1)

from sqlalchemy import create_engine, text

engine = create_engine(DATABASE_URL)

MIGRATIONS = [
    (
        "Expand quick_codes.code from VARCHAR(3) to VARCHAR(6)",
        "ALTER TABLE quick_codes ALTER COLUMN code TYPE VARCHAR(6);",
    ),
    (
        "Add prescriptions.picture_path column",
        "ALTER TABLE prescriptions ADD COLUMN IF NOT EXISTS picture_path VARCHAR;",
    ),
    (
        "Add index on refills.patient_id",
        "CREATE INDEX IF NOT EXISTS ix_refills_patient_id ON refills(patient_id);",
    ),
]


def run():
    with engine.connect() as conn:
        for description, sql in MIGRATIONS:
            print(f"  → {description}...", end=" ", flush=True)
            try:
                conn.execute(text(sql))
                conn.commit()
                print("OK")
            except Exception as e:
                print(f"FAILED: {e}")
                raise


if __name__ == "__main__":
    print("Running v2 schema migrations...")
    run()
    print("Done.")

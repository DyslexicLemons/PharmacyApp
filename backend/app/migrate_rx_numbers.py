"""
Migration: renumber prescription IDs to 17XXXXX format (7 digits, starting with 17).

Existing IDs (3-4 digits) are remapped by adding 1,700,000:
  e.g.  1 → 1700001,  123 → 1700123,  9999 → 1709999

All foreign-key references in refills, refill_hist, and audit_log are
updated to match.  The prescriptions sequence is advanced past the
highest new ID so new inserts continue naturally.

Run once:
    cd backend
    python -m app.migrate_rx_numbers
"""
from sqlalchemy import text
from .database import engine

OFFSET = 1_700_000


def run():
    with engine.connect() as conn:
        # Check if there are any prescriptions
        max_id = conn.execute(text("SELECT MAX(id) FROM prescriptions")).scalar()
        if max_id is None:
            print("No prescriptions found — nothing to migrate.")
            return

        min_id = conn.execute(text("SELECT MIN(id) FROM prescriptions")).scalar()

        # Idempotency check: if already migrated, skip
        if min_id >= OFFSET:
            print(f"Prescriptions already use 17XXXXX format (min id={min_id}). Skipping.")
            return

        if OFFSET + max_id > 9_999_999:
            raise ValueError(
                f"Cannot migrate: {OFFSET} + {max_id} = {OFFSET + max_id} exceeds 7 digits."
            )

        count = conn.execute(text("SELECT COUNT(*) FROM prescriptions")).scalar()
        print(f"Migrating {count} prescriptions (id range {min_id}–{max_id} → {OFFSET + min_id}–{OFFSET + max_id})...")

        # --- Find FK constraints that reference prescriptions.id dynamically ---
        fk_rows = conn.execute(text("""
            SELECT tc.constraint_name, tc.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.referential_constraints rc
                ON tc.constraint_name = rc.constraint_name
                AND tc.table_schema = rc.constraint_schema
            JOIN information_schema.key_column_usage ccu
                ON rc.unique_constraint_name = ccu.constraint_name
                AND rc.unique_constraint_schema = ccu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND ccu.table_name = 'prescriptions'
                AND ccu.column_name = 'id'
        """)).fetchall()

        # Drop all FK constraints pointing at prescriptions.id
        for constraint_name, table_name, col_name in fk_rows:
            conn.execute(text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT "{constraint_name}"'))
            print(f"  Dropped FK: {table_name}.{constraint_name}")

        # Update primary key on prescriptions
        conn.execute(text(f"UPDATE prescriptions SET id = id + {OFFSET}"))
        print(f"  Updated prescriptions.id  (+{OFFSET})")

        # Update every FK column that was referencing prescriptions.id
        for constraint_name, table_name, col_name in fk_rows:
            conn.execute(text(
                f'UPDATE "{table_name}" SET "{col_name}" = "{col_name}" + {OFFSET} '
                f'WHERE "{col_name}" IS NOT NULL'
            ))
            print(f"  Updated {table_name}.{col_name}")

        # audit_log.prescription_id is a plain integer (no FK constraint) — update separately.
        # The immutable trigger must be disabled for this one-time backfill, then re-enabled.
        audit_cols = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'audit_log' AND column_name = 'prescription_id'
        """)).fetchone()
        if audit_cols:
            conn.execute(text("ALTER TABLE audit_log DISABLE TRIGGER trg_audit_log_immutable"))
            conn.execute(text(
                f"UPDATE audit_log SET prescription_id = prescription_id + {OFFSET} "
                f"WHERE prescription_id IS NOT NULL"
            ))
            conn.execute(text("ALTER TABLE audit_log ENABLE TRIGGER trg_audit_log_immutable"))
            print("  Updated audit_log.prescription_id")

        # Re-add FK constraints
        for constraint_name, table_name, col_name in fk_rows:
            conn.execute(text(
                f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" '
                f'FOREIGN KEY ("{col_name}") REFERENCES prescriptions(id)'
            ))
            print(f"  Re-added FK: {table_name}.{constraint_name}")

        # Advance the PostgreSQL sequence so new inserts start after the highest migrated ID
        seq_name = conn.execute(text(
            "SELECT pg_get_serial_sequence('prescriptions', 'id')"
        )).scalar()
        if seq_name:
            conn.execute(text(f"SELECT setval('{seq_name}', {OFFSET + max_id}, true)"))
            print(f"  Advanced sequence '{seq_name}' to {OFFSET + max_id}")
        else:
            print("  WARNING: could not find sequence for prescriptions.id — set it manually if needed.")

        conn.commit()
        print("Migration complete.")


if __name__ == "__main__":
    run()

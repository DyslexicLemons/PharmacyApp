"""
Migration: add city and state columns to patients table,
then backfill existing rows with randomly assigned US cities/states.

Run once:
    cd backend
    python -m app.migrate_add_city_state
"""
import random
from sqlalchemy import text
from .database import engine, SessionLocal

CITY_STATE_PAIRS = [
    ("Phoenix", "AZ"), ("Tucson", "AZ"), ("Mesa", "AZ"),
    ("Los Angeles", "CA"), ("San Diego", "CA"), ("San Francisco", "CA"), ("Sacramento", "CA"),
    ("Denver", "CO"), ("Colorado Springs", "CO"),
    ("Jacksonville", "FL"), ("Miami", "FL"), ("Tampa", "FL"), ("Orlando", "FL"),
    ("Atlanta", "GA"), ("Savannah", "GA"),
    ("Chicago", "IL"), ("Aurora", "IL"),
    ("Indianapolis", "IN"),
    ("Louisville", "KY"),
    ("New Orleans", "LA"), ("Baton Rouge", "LA"),
    ("Boston", "MA"), ("Worcester", "MA"),
    ("Detroit", "MI"), ("Grand Rapids", "MI"),
    ("Minneapolis", "MN"),
    ("Kansas City", "MO"), ("St. Louis", "MO"),
    ("Charlotte", "NC"), ("Raleigh", "NC"),
    ("Las Vegas", "NV"), ("Reno", "NV"),
    ("Newark", "NJ"), ("Jersey City", "NJ"),
    ("Albuquerque", "NM"),
    ("New York", "NY"), ("Buffalo", "NY"), ("Rochester", "NY"),
    ("Columbus", "OH"), ("Cleveland", "OH"), ("Cincinnati", "OH"),
    ("Oklahoma City", "OK"), ("Tulsa", "OK"),
    ("Portland", "OR"),
    ("Philadelphia", "PA"), ("Pittsburgh", "PA"),
    ("Memphis", "TN"), ("Nashville", "TN"),
    ("Houston", "TX"), ("San Antonio", "TX"), ("Dallas", "TX"), ("Austin", "TX"),
    ("Salt Lake City", "UT"),
    ("Virginia Beach", "VA"), ("Richmond", "VA"),
    ("Seattle", "WA"), ("Spokane", "WA"),
    ("Milwaukee", "WI"),
]


def run():
    with engine.connect() as conn:
        # Add columns if they don't already exist
        existing_cols = {
            row[0]
            for row in conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='patients'")
            )
        }

        if "city" not in existing_cols:
            conn.execute(text("ALTER TABLE patients ADD COLUMN city VARCHAR"))
            print("Added column: city")
        else:
            print("Column city already exists, skipping.")

        if "state" not in existing_cols:
            conn.execute(text("ALTER TABLE patients ADD COLUMN state VARCHAR"))
            print("Added column: state")
        else:
            print("Column state already exists, skipping.")

        conn.commit()

    # Backfill existing patients that have no city/state
    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT id FROM patients WHERE city IS NULL OR state IS NULL")
        ).fetchall()

        for (pid,) in rows:
            city, state = random.choice(CITY_STATE_PAIRS)
            db.execute(
                text("UPDATE patients SET city = :city, state = :state WHERE id = :id"),
                {"city": city, "state": state, "id": pid},
            )

        db.commit()
        print(f"Backfilled {len(rows)} patient(s) with random city/state.")
    finally:
        db.close()


if __name__ == "__main__":
    run()

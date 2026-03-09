"""
Migration: Create users table and add a default admin user.

Usage:
    cd backend
    python -m app.migrate_add_users

Default credentials:  username=admin  password=admin
Change the password after first login by running this script with custom values,
or update the hashed_password in the database directly.
"""

import sys
import bcrypt
from .database import engine, SessionLocal
from .models import Base, User

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"


def run(username: str = DEFAULT_USERNAME, password: str = DEFAULT_PASSWORD):
    # Create the users table if it doesn't exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            print(f"User '{username}' already exists — skipping creation.")
            return

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = User(username=username, hashed_password=hashed, is_active=True, is_admin=(username == DEFAULT_USERNAME))
        db.add(user)
        db.commit()
        print(f"Created user '{username}' with the provided password.")
        print("IMPORTANT: Change the default password after first login!")
    finally:
        db.close()


if __name__ == "__main__":
    username = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_USERNAME
    password = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PASSWORD
    run(username, password)

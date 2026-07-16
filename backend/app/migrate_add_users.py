"""
Migration: Create users table and add a default admin user.

Usage:
    cd backend
    python -m app.migrate_add_users [username] [password]

If no password is given, a random one is generated and printed once —
there is no static default to leave unrotated. Change it after first login,
or pass an explicit password as the second argument.
"""

import secrets
import sys
import bcrypt
from .database import engine, SessionLocal
from .models import Base, User

DEFAULT_USERNAME = "admin"


def run(username: str = DEFAULT_USERNAME, password: str | None = None):
    # Create the users table if it doesn't exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            print(f"User '{username}' already exists — skipping creation.")
            return

        generated = password is None
        if generated:
            password = secrets.token_urlsafe(18)

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = User(username=username, hashed_password=hashed, is_active=True, is_admin=(username == DEFAULT_USERNAME))
        db.add(user)
        db.commit()
        if generated:
            print(f"Created user '{username}' with generated password: {password}")
            print("This password is shown only once — change it after first login.")
        else:
            print(f"Created user '{username}' with the provided password.")
            print("IMPORTANT: Change the default password after first login!")
    finally:
        db.close()


if __name__ == "__main__":
    username = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_USERNAME
    password = sys.argv[2] if len(sys.argv) > 2 else None
    run(username, password)

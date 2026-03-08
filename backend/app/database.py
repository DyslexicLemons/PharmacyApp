import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Load DATABASE_URL from the environment.
# Set this in a .env file or your shell before starting the server.
# Example: DATABASE_URL=postgresql://postgres:password@localhost/pharmacy_db
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:6789@localhost/pharmacy_db"  # fallback for local dev
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

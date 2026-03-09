import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()
from sqlalchemy.orm import sessionmaker, declarative_base

# DATABASE_URL must be set in the environment — no insecure fallback.
# Example: DATABASE_URL=postgresql://postgres:password@localhost/pharmacy_db
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is required.\n"
        "Example: DATABASE_URL=postgresql://postgres:password@localhost/pharmacy_db"
    )

engine = create_engine(
    DATABASE_URL,
    pool_size=10,        # max persistent connections in the pool
    max_overflow=20,     # extra connections allowed above pool_size under load
    pool_timeout=30,     # seconds to wait for a connection before raising
    pool_recycle=1800,   # recycle connections after 30 min to avoid stale-connection errors
    pool_pre_ping=True,  # verify connection is alive before use (handles DB restarts)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

"""Alembic environment configuration.

Reads DATABASE_URL from the environment (via python-dotenv / AWS Secrets) so
credentials never appear in source control.

Usage (from backend/ directory):
  alembic upgrade head
  alembic revision --autogenerate -m "add_foo_column"
  alembic downgrade -1
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# ---------------------------------------------------------------------------
# Make sure the backend package is importable when alembic is run from the
# backend/ directory (e.g. `alembic upgrade head`).
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env so DATABASE_URL is available when running locally.
from dotenv import load_dotenv
load_dotenv()

# Load AWS Secrets if configured (no-op in local/CI environments).
from app.secrets import load_aws_secrets
load_aws_secrets()

# Import the Base metadata so autogenerate can diff against our models.
from app.database import Base  # noqa: F401 — registers all models
import app.models  # noqa: F401 — ensure all model classes are loaded into Base.metadata

# ---------------------------------------------------------------------------
# Alembic Config object from alembic.ini
# ---------------------------------------------------------------------------
config = context.config

# Inject DATABASE_URL at runtime so we never store it in alembic.ini.
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    raise RuntimeError(
        "DATABASE_URL environment variable is required to run Alembic migrations.\n"
        "Example: DATABASE_URL=postgresql://postgres:password@localhost/pharmacy_db"
    )
config.set_main_option("sqlalchemy.url", db_url)

# Set up Python logging as declared in alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Run migrations in "offline" mode (no live DB connection — just emit SQL)
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Run migrations in "online" mode (live DB connection)
# ---------------------------------------------------------------------------
def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

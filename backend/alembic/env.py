"""Alembic environment configuration.

Reads DATABASE_URL from .env (via python-dotenv) so the connection string
is never hardcoded in alembic.ini or version files.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Make sure the src/ package is importable ──────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ── Load .env ─────────────────────────────────────────────────────────────────
# python-dotenv is a transitive dep of pydantic-settings, always available.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # will fall back to real environment variables

# ── Alembic Config object ──────────────────────────────────────────────────────
config = context.config

# Inject DATABASE_URL from the environment so alembic.ini stays secret-free
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it to your .env file.\n"
        "Format: postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres"
    )
# configparser uses % for interpolation, so percent-encoded characters in the
# URL (e.g. %24 for $, %2B for +) must be escaped as %% before being stored.
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# We use raw SQL in migrations (no SQLAlchemy ORM models), so target_metadata is None
target_metadata = None


# ── Offline mode (generates SQL script without connecting) ────────────────────

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Useful for generating a SQL script to review before applying.
    Usage: alembic upgrade head --sql > migrations.sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode (connects and applies migrations directly) ────────────────────

def run_migrations_online() -> None:
    """Run migrations in 'online' mode (default)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # don't pool connections for migrations
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

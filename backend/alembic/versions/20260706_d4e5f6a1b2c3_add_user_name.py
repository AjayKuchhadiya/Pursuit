"""Add name column to users table.

Revision ID: d4e5f6a1b2c3
Revises: c3d4e5f6a1b2
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "d4e5f6a1b2c3"
down_revision: Union[str, None] = "c3d4e5f6a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable first so existing rows aren't blocked
    op.execute("ALTER TABLE public.users ADD COLUMN IF NOT EXISTS name TEXT")
    # Backfill existing rows with a unique random placeholder each
    op.execute("""
        UPDATE public.users
        SET name = 'User_' || upper(left(replace(gen_random_uuid()::text, '-', ''), 6))
        WHERE name IS NULL
    """)
    # Enforce NOT NULL and set a default for future inserts that omit it
    op.execute("ALTER TABLE public.users ALTER COLUMN name SET NOT NULL")
    op.execute("""
        ALTER TABLE public.users
        ALTER COLUMN name SET DEFAULT 'User_' || upper(left(replace(gen_random_uuid()::text, '-', ''), 6))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE public.users DROP COLUMN IF EXISTS name")

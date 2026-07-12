"""Add last_morning_sent and last_evening_sent to users for send deduplication.

Prevents duplicate messages when the scheduler fires multiple times within
a widened time window (needed to survive Render free-tier process restarts).

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-12 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        alter table public.users
            add column if not exists last_morning_sent date,
            add column if not exists last_evening_sent date;
    """)


def downgrade() -> None:
    op.execute("""
        alter table public.users
            drop column if exists last_morning_sent,
            drop column if exists last_evening_sent;
    """)

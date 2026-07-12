"""Add status and completed_at to schedules.

status: 'active' | 'paused' | 'completed'
completed_at: timestamp set when a goal is marked completed

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-07-12 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        alter table public.schedules
            add column if not exists status text not null default 'active'
                check (status in ('active', 'paused', 'completed')),
            add column if not exists completed_at timestamptz;
    """)


def downgrade() -> None:
    op.execute("""
        alter table public.schedules
            drop column if exists completed_at,
            drop column if exists status;
    """)

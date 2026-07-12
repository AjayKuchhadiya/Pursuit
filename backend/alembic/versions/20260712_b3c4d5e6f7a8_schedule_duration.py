"""Add duration_minutes to schedules.

Users can now specify how long they plan to spend on a goal each day.
Defaults to 60 minutes for existing rows.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-07-12 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        alter table public.schedules
            add column if not exists duration_minutes integer not null default 60;
    """)


def downgrade() -> None:
    op.execute("""
        alter table public.schedules
            drop column if exists duration_minutes;
    """)

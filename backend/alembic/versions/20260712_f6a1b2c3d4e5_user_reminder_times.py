"""Move morning_time and evening_time from schedules to users.

Reminder times are now a single user-level setting, not per-task.
The cron/scheduler reads the user's one time and sends a consolidated
message covering all active tasks.

Revision ID: f6a1b2c3d4e5
Revises: e5f6a1b2c3d4
Create Date: 2026-07-12 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "f6a1b2c3d4e5"
down_revision: Union[str, None] = "e5f6a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add reminder time columns to users (with sensible defaults)
    op.execute("""
        alter table public.users
            add column if not exists morning_time time not null default '08:00',
            add column if not exists evening_time time not null default '21:00'
    """)

    # Drop per-schedule reminder times (no longer needed)
    op.execute("""
        alter table public.schedules
            drop column if exists morning_time,
            drop column if exists evening_time
    """)


def downgrade() -> None:
    # Restore per-schedule columns with defaults
    op.execute("""
        alter table public.schedules
            add column if not exists morning_time time not null default '08:00',
            add column if not exists evening_time time not null default '21:00'
    """)

    # Remove user-level columns
    op.execute("""
        alter table public.users
            drop column if exists morning_time,
            drop column if exists evening_time
    """)

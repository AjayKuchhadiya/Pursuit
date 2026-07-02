"""Multi-schedule support – reminder times and per-schedule log constraint.

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-06-22 01:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6a1"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add per-schedule reminder times
    op.execute("""
        alter table public.schedules
            add column if not exists morning_time time not null default '08:00',
            add column if not exists evening_time time not null default '21:00'
    """)

    # Replace the one-log-per-user-per-day constraint with
    # one-log-per-user-per-SCHEDULE-per-day to support multiple schedules
    op.execute(
        "alter table public.daily_logs "
        "drop constraint if exists daily_logs_user_id_log_date_key"
    )
    op.execute("""
        alter table public.daily_logs
            add constraint daily_logs_user_schedule_date_key
            unique (user_id, schedule_id, log_date)
    """)


def downgrade() -> None:
    op.execute(
        "alter table public.daily_logs "
        "drop constraint if exists daily_logs_user_schedule_date_key"
    )
    op.execute("""
        alter table public.daily_logs
            add constraint daily_logs_user_id_log_date_key
            unique (user_id, log_date)
    """)
    op.execute("""
        alter table public.schedules
            drop column if exists morning_time,
            drop column if exists evening_time
    """)

"""Initial schema – all 7 tables.

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-06-22 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("create extension if not exists pgcrypto")

    op.execute("""
        do $$ begin
            create type personality_enum as enum ('cheerleader', 'drill_sergeant', 'analyst');
        exception when duplicate_object then null;
        end $$
    """)

    op.execute("""
        create table if not exists public.users (
            id           uuid primary key default gen_random_uuid(),
            phone_number text not null unique,
            personality  personality_enum not null default 'analyst',
            timezone     text not null default 'Asia/Kolkata',
            is_active    boolean not null default true,
            created_at   timestamptz not null default now()
        )
    """)

    op.execute("""
        create table if not exists public.schedules (
            id         uuid primary key default gen_random_uuid(),
            user_id    uuid not null references public.users(id) on delete cascade,
            title      text not null,
            is_active  boolean not null default true,
            created_at timestamptz not null default now()
        )
    """)
    op.execute(
        "create index if not exists schedules_user_id_idx on public.schedules(user_id)"
    )

    op.execute("""
        create table if not exists public.daily_logs (
            id               uuid primary key default gen_random_uuid(),
            user_id          uuid not null references public.users(id) on delete cascade,
            schedule_id      uuid not null references public.schedules(id) on delete cascade,
            log_date         date not null,
            completion_pct   smallint not null check (completion_pct between 0 and 100),
            is_casual_leave  boolean not null default false,
            created_at       timestamptz not null default now(),
            unique(user_id, log_date)
        )
    """)
    op.execute(
        "create index if not exists daily_logs_user_date_idx "
        "on public.daily_logs(user_id, log_date desc)"
    )

    op.execute("""
        create table if not exists public.leave_balance (
            user_id    uuid primary key references public.users(id) on delete cascade,
            balance    numeric(4, 1) not null default 3.0 check (balance >= 0),
            updated_at timestamptz not null default now()
        )
    """)

    op.execute("""
        create table if not exists public.streaks (
            user_id          uuid primary key references public.users(id) on delete cascade,
            current_streak   integer not null default 0,
            all_time_high    integer not null default 0,
            last_active_date date,
            updated_at       timestamptz not null default now()
        )
    """)

    op.execute("""
        do $$ begin
            create type condition_type_enum as enum
                ('streak_days', 'weekly_avg_pct', 'total_days');
        exception when duplicate_object then null;
        end $$
    """)

    op.execute("""
        create table if not exists public.rewards (
            id              uuid primary key default gen_random_uuid(),
            user_id         uuid not null references public.users(id) on delete cascade,
            title           text not null,
            condition_type  condition_type_enum not null,
            condition_value numeric(8, 2) not null,
            is_unlocked     boolean not null default false,
            created_at      timestamptz not null default now()
        )
    """)

    op.execute("""
        create table if not exists public.otp_sessions (
            id           uuid primary key default gen_random_uuid(),
            phone_number text not null,
            otp_hash     text not null,
            expires_at   timestamptz not null,
            is_used      boolean not null default false,
            created_at   timestamptz not null default now()
        )
    """)
    op.execute(
        "create index if not exists otp_sessions_phone_idx "
        "on public.otp_sessions(phone_number, is_used, expires_at)"
    )

    # Enable Row Level Security on all tables
    for table in [
        "users", "schedules", "daily_logs", "leave_balance",
        "streaks", "rewards", "otp_sessions",
    ]:
        op.execute(f"alter table public.{table} enable row level security")


def downgrade() -> None:
    for table in [
        "otp_sessions", "rewards", "streaks", "leave_balance",
        "daily_logs", "schedules", "users",
    ]:
        op.execute(f"drop table if exists public.{table} cascade")

    op.execute("drop type if exists condition_type_enum")
    op.execute("drop type if exists personality_enum")

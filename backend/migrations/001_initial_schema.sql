-- Pursuit database schema
-- Run each section in order in the Supabase SQL Editor.
-- Enable pgcrypto for gen_random_uuid()
create extension if not exists pgcrypto;

-- ── 1. users ──────────────────────────────────────────────────────────────────
create type personality_enum as enum ('cheerleader', 'drill_sergeant', 'analyst');

create table if not exists public.users (
    id           uuid primary key default gen_random_uuid(),
    phone_number text not null unique,
    personality  personality_enum not null default 'analyst',
    timezone     text not null default 'Asia/Kolkata',
    is_active    boolean not null default true,
    created_at   timestamptz not null default now()
);

-- ── 2. schedules ──────────────────────────────────────────────────────────────
create table if not exists public.schedules (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid not null references public.users(id) on delete cascade,
    title      text not null,
    is_active  boolean not null default true,
    created_at timestamptz not null default now()
);

create index if not exists schedules_user_id_idx on public.schedules(user_id);

-- ── 3. daily_logs ─────────────────────────────────────────────────────────────
create table if not exists public.daily_logs (
    id               uuid primary key default gen_random_uuid(),
    user_id          uuid not null references public.users(id) on delete cascade,
    schedule_id      uuid not null references public.schedules(id) on delete cascade,
    log_date         date not null,
    completion_pct   smallint not null check (completion_pct between 0 and 100),
    is_casual_leave  boolean not null default false,
    created_at       timestamptz not null default now(),
    -- one log per user per day
    unique(user_id, log_date)
);

create index if not exists daily_logs_user_date_idx on public.daily_logs(user_id, log_date desc);

-- ── 4. leave_balance ──────────────────────────────────────────────────────────
create table if not exists public.leave_balance (
    user_id    uuid primary key references public.users(id) on delete cascade,
    balance    numeric(4, 1) not null default 3.0 check (balance >= 0),
    updated_at timestamptz not null default now()
);

-- ── 5. streaks ────────────────────────────────────────────────────────────────
create table if not exists public.streaks (
    user_id          uuid primary key references public.users(id) on delete cascade,
    current_streak   integer not null default 0,
    all_time_high    integer not null default 0,
    last_active_date date,
    updated_at       timestamptz not null default now()
);

-- ── 6. rewards ────────────────────────────────────────────────────────────────
create type condition_type_enum as enum ('streak_days', 'weekly_avg_pct', 'total_days');

create table if not exists public.rewards (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references public.users(id) on delete cascade,
    title           text not null,
    condition_type  condition_type_enum not null,
    condition_value numeric(8, 2) not null,
    is_unlocked     boolean not null default false,
    created_at      timestamptz not null default now()
);

-- ── 7. otp_sessions ───────────────────────────────────────────────────────────
create table if not exists public.otp_sessions (
    id           uuid primary key default gen_random_uuid(),
    phone_number text not null,
    otp_hash     text not null,
    expires_at   timestamptz not null,
    is_used      boolean not null default false,
    created_at   timestamptz not null default now()
);

create index if not exists otp_sessions_phone_idx on public.otp_sessions(phone_number, is_used, expires_at);

-- ── Row Level Security ────────────────────────────────────────────────────────
-- All tables use the service role key server-side (bypasses RLS).
-- Enable RLS so the anon key cannot be used to read data directly.
alter table public.users           enable row level security;
alter table public.schedules       enable row level security;
alter table public.daily_logs      enable row level security;
alter table public.leave_balance   enable row level security;
alter table public.streaks         enable row level security;
alter table public.rewards         enable row level security;
alter table public.otp_sessions    enable row level security;

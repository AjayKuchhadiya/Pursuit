-- Migration 002: multi-schedule support + reminder times
-- Run in Supabase SQL Editor after 001_initial_schema.sql

-- ── 1. Add reminder times to schedules ───────────────────────────────────────
-- morning_time: when the agenda is sent (HH:MM, 24h, user's local time)
-- evening_time: when the check-in card is sent (HH:MM, 24h, user's local time)
alter table public.schedules
    add column if not exists morning_time time not null default '08:00',
    add column if not exists evening_time time not null default '21:00';

-- ── 2. Fix daily_logs unique constraint to support multiple schedules per day ─
-- Drop the old one-log-per-user-per-day constraint
alter table public.daily_logs
    drop constraint if exists daily_logs_user_id_log_date_key;

-- One log per user per SCHEDULE per day
alter table public.daily_logs
    add constraint daily_logs_user_schedule_date_key
    unique (user_id, schedule_id, log_date);

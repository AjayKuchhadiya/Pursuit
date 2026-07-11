"""Background scheduler – fires morning and evening WhatsApp pings at exact times.

Runs inside the FastAPI process.  Started/stopped in the application lifespan
so jobs fire to the exact minute, fully timezone-aware, for every active user.

Design
------
Two jobs run on a CronTrigger(second=0) — i.e., at second :00 of every minute.
Each job fetches all active users, checks if any schedule's morning_time (or
evening_time) matches the current HH:MM in the user's own timezone, and sends
the WhatsApp message only to those users.  Users in different timezones are all
handled by the same two jobs without any extra configuration.
"""

from __future__ import annotations

import zoneinfo
from collections import Counter
from datetime import date, datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import get_supabase
from services import ai_agent, whatsapp

logger = structlog.get_logger(__name__)

# Single shared scheduler instance — started once in lifespan
scheduler = AsyncIOScheduler(timezone="UTC")


# ── Morning job ───────────────────────────────────────────────────────────────

async def _morning_job() -> None:
    """Fire every minute; send morning messages to users whose time matches now."""
    db = await get_supabase()

    users_res = (
        await db.table("users")
        .select("id, phone_number, timezone, personality, name, morning_time")
        .eq("is_active", True)
        .execute()
    )
    sent = errors = 0

    for user in users_res.data or []:
        user_id: str = user["id"]
        phone: str = user["phone_number"]
        tz_str: str = user.get("timezone") or "Asia/Kolkata"
        personality: str = user.get("personality") or "analyst"
        user_name: str = user.get("name") or "there"
        user_morning: str = user.get("morning_time") or "08:00"

        try:
            tz = zoneinfo.ZoneInfo(tz_str)
        except zoneinfo.ZoneInfoNotFoundError:
            tz = zoneinfo.ZoneInfo("Asia/Kolkata")

        now = datetime.now(tz)

        # Only send if it is the user's morning reminder time
        if not _time_matches(user_morning, now):
            continue

        sched_res = (
            await db.table("schedules")
            .select("id, title, days_of_week")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .execute()
        )

        due = [
            s for s in (sched_res.data or [])
            if now.weekday() in (s.get("days_of_week") or list(range(7)))
        ]

        if not due:
            continue

        streak_res = (
            await db.table("streaks")
            .select("current_streak")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        streak = int(((streak_res.data or [{}])[0] or {}).get("current_streak", 0))

        try:
            msg = await ai_agent.generate_morning_msg(
                user_name=user_name,
                streak=streak,
                schedules=[s["title"] for s in due],
                personality=personality,
            )
            await whatsapp.send_text_message(phone, msg)
            sent += 1
            logger.info("scheduler.morning_sent", user_id=user_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("scheduler.morning_failed", user_id=user_id, error=str(exc))
            errors += 1

    if sent or errors:
        logger.info("scheduler.morning_job_complete", sent=sent, errors=errors)


# ── Evening job ───────────────────────────────────────────────────────────────

async def _evening_job() -> None:
    """Fire every minute; send evening check-in to users whose time matches now."""
    db = await get_supabase()
    today = date.today().isoformat()

    users_res = (
        await db.table("users")
        .select("id, phone_number, timezone, personality, name, evening_time")
        .eq("is_active", True)
        .execute()
    )
    sent = errors = 0

    for user in users_res.data or []:
        user_id: str = user["id"]
        phone: str = user["phone_number"]
        tz_str: str = user.get("timezone") or "Asia/Kolkata"
        personality: str = user.get("personality") or "analyst"
        user_name: str = user.get("name") or "there"
        user_evening: str = user.get("evening_time") or "21:00"

        try:
            tz = zoneinfo.ZoneInfo(tz_str)
        except zoneinfo.ZoneInfoNotFoundError:
            tz = zoneinfo.ZoneInfo("Asia/Kolkata")

        now = datetime.now(tz)

        # Only send if it is the user's evening reminder time
        if not _time_matches(user_evening, now):
            continue

        sched_res = (
            await db.table("schedules")
            .select("id, title, days_of_week")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .execute()
        )

        due: list[dict] = []
        for s in sched_res.data or []:
            days = s.get("days_of_week") or list(range(7))
            if now.weekday() not in days:
                continue
            # Skip if already logged today
            logged = (
                await db.table("daily_logs")
                .select("id")
                .eq("user_id", user_id)
                .eq("schedule_id", s["id"])
                .eq("log_date", today)
                .execute()
            )
            if not logged.data:
                due.append(s)

        if not due:
            continue

        bal_res = (
            await db.table("leave_balance")
            .select("balance")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        cl_balance = float(((bal_res.data or [{}])[0] or {}).get("balance", 3.0))

        streak_res = (
            await db.table("streaks")
            .select("current_streak")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        streak = int(((streak_res.data or [{}])[0] or {}).get("current_streak", 0))

        try:
            title_counts = Counter(s["title"] for s in due)
            display_titles = [
                f"{title} (×{count})" if count > 1 else title
                for title, count in title_counts.items()
            ]
            body = await ai_agent.generate_evening_prompt(
                user_name=user_name,
                streak=streak,
                schedules=display_titles,
                personality=personality,
                cl_balance=cl_balance,
            )
            await whatsapp.send_consolidated_evening_checkin(phone=phone, body_text=body)
            sent += 1
            logger.info("scheduler.evening_sent", user_id=user_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("scheduler.evening_failed", user_id=user_id, error=str(exc))
            errors += 1

    if sent or errors:
        logger.info("scheduler.evening_job_complete", sent=sent, errors=errors)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _time_matches(hhmm: str, now: datetime, lead_minutes: int = 2) -> bool:
    """Return True if now is exactly `lead_minutes` before 'HH:MM'.

    Firing early gives the server time to generate and deliver the message
    so it arrives at the user's chosen time.
    """
    try:
        h, m = map(int, hhmm.split(":")[:2])
    except (ValueError, AttributeError):
        return False
    target_mins = (h * 60 + m - lead_minutes) % (24 * 60)
    now_mins = now.hour * 60 + now.minute
    return now_mins == target_mins


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """Register jobs and start the scheduler. Called once from the app lifespan."""
    _trigger = CronTrigger(second=0)  # fires at :00 of every minute

    scheduler.add_job(
        _morning_job,
        _trigger,
        id="morning_job",
        replace_existing=True,
        misfire_grace_time=60,  # fire up to 60 s late (covers slow Render boot)
        coalesce=True,          # if multiple misfires queued, fire only once
    )
    scheduler.add_job(
        _evening_job,
        _trigger,
        id="evening_job",
        replace_existing=True,
        misfire_grace_time=60,
        coalesce=True,
    )
    scheduler.start()
    logger.info("scheduler.started")


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler. Called from the app lifespan on exit."""
    scheduler.shutdown(wait=False)
    logger.info("scheduler.stopped")

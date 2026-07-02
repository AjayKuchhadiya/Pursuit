"""Cron router – secured endpoints called by GitHub Actions.

Two endpoints:
  POST /cron/morning-ping  – sends the daily agenda at each user's morning_time
  POST /cron/evening-ping  – sends per-schedule check-in cards at each user's evening_time

Both are called every 30 minutes by GitHub Actions; they filter to only
message users whose configured time falls within the current 30-minute window
(in the user's own timezone).
"""

from __future__ import annotations

import zoneinfo
from datetime import date, datetime, time

import structlog
from fastapi import APIRouter, Header, HTTPException, status

from config import settings
from database import SupabaseDep
from services import whatsapp

router = APIRouter(prefix="/cron", tags=["cron"])
logger = structlog.get_logger(__name__)

WINDOW_MINUTES = 30  # fire if user's configured time is within this window


def _in_window(target: time, user_tz: str) -> bool:
    """Return True if *target* (HH:MM local) is within the next WINDOW_MINUTES."""
    try:
        tz = zoneinfo.ZoneInfo(user_tz)
    except zoneinfo.ZoneInfoNotFoundError:
        tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    now = datetime.now(tz).time()
    now_mins = now.hour * 60 + now.minute
    target_mins = target.hour * 60 + target.minute
    return 0 <= (target_mins - now_mins) < WINDOW_MINUTES


def _guard(secret: str) -> None:
    if secret != settings.cron_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


# ── Morning ping ──────────────────────────────────────────────────────────────

@router.post("/morning-ping", status_code=status.HTTP_200_OK)
async def morning_ping(
    db: SupabaseDep,
    x_cron_secret: str = Header(alias="X-Cron-Secret"),
) -> dict:  # type: ignore[type-arg]
    """Send each user their daily agenda listing all active schedules.

    Only messages users whose ``morning_time`` falls in the current 30-min window.
    """
    _guard(x_cron_secret)

    users_res = (
        await db.table("users")
        .select("id, phone_number, timezone")
        .eq("is_active", True)
        .execute()
    )
    users = users_res.data or []
    sent = errors = 0

    for user in users:
        user_id: str = user["id"]
        phone: str = user["phone_number"]
        tz: str = user.get("timezone") or "Asia/Kolkata"

        # Fetch all active schedules for this user
        sched_res = (
            await db.table("schedules")
            .select("id, title, morning_time, days_of_week")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .execute()
        )
        schedules = sched_res.data or []
        if not schedules:
            continue

        # Determine today's weekday in the user's timezone (0=Mon … 6=Sun)
        try:
            tz_obj = zoneinfo.ZoneInfo(tz)
        except zoneinfo.ZoneInfoNotFoundError:
            tz_obj = zoneinfo.ZoneInfo("Asia/Kolkata")
        today_weekday = datetime.now(tz_obj).weekday()

        # Keep only schedules active today and within the morning_time window
        due = [
            s for s in schedules
            if today_weekday in (s.get("days_of_week") or list(range(7)))
            and _in_window(
                time(*map(int, (s.get("morning_time") or "08:00").split(":")[:2])),
                tz,
            )
        ]
        if not due:
            continue

        titles = [s["title"] for s in due]
        try:
            await whatsapp.send_morning_agenda(phone=phone, schedules=titles)
            sent += 1
        except Exception as exc:
            logger.error("cron.morning_ping_failed", user_id=user_id, error=str(exc))
            errors += 1

    logger.info("cron.morning_ping_complete", sent=sent, errors=errors)
    return {"sent": sent, "errors": errors}


# ── Evening ping ──────────────────────────────────────────────────────────────

@router.post("/evening-ping", status_code=status.HTTP_200_OK)
async def evening_ping(
    db: SupabaseDep,
    x_cron_secret: str = Header(alias="X-Cron-Secret"),
) -> dict:  # type: ignore[type-arg]
    """Send each user one interactive check-in card per active schedule.

    Only messages users whose schedule's ``evening_time`` falls in the
    current 30-min window.  Skips schedules already logged today.
    """
    _guard(x_cron_secret)

    today = date.today().isoformat()

    users_res = (
        await db.table("users")
        .select("id, phone_number, timezone, personality")
        .eq("is_active", True)
        .execute()
    )
    users = users_res.data or []
    sent = errors = 0

    for user in users:
        user_id: str = user["id"]
        phone: str = user["phone_number"]
        tz: str = user.get("timezone") or "Asia/Kolkata"

        sched_res = (
            await db.table("schedules")
            .select("id, title, evening_time, days_of_week")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .execute()
        )
        schedules = sched_res.data or []
        if not schedules:
            continue

        # Today's weekday in user's timezone
        try:
            tz_obj = zoneinfo.ZoneInfo(tz)
        except zoneinfo.ZoneInfoNotFoundError:
            tz_obj = zoneinfo.ZoneInfo("Asia/Kolkata")
        today_weekday = datetime.now(tz_obj).weekday()

        bal_res = (
            await db.table("leave_balance")
            .select("balance")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        cl_balance = float(((bal_res.data or [{}])[0] or {}).get("balance", 3.0))

        for schedule in schedules:
            schedule_id: str = schedule["id"]
            evening_time_str: str = schedule.get("evening_time") or "21:00"
            h, m = map(int, evening_time_str.split(":")[:2])

            # Skip if not scheduled for today
            days = schedule.get("days_of_week") or list(range(7))
            if today_weekday not in days:
                continue

            if not _in_window(time(h, m), tz):
                continue

            # Skip if already logged today
            logged_res = (
                await db.table("daily_logs")
                .select("id")
                .eq("user_id", user_id)
                .eq("schedule_id", schedule_id)
                .eq("log_date", today)
                .execute()
            )
            if logged_res.data:
                continue

            try:
                await whatsapp.send_interactive_checkin(
                    phone=phone,
                    schedule_id=schedule_id,
                    schedule_title=schedule["title"],
                    cl_balance=cl_balance,
                )
                sent += 1
            except Exception as exc:
                logger.error(
                    "cron.evening_ping_failed",
                    user_id=user_id,
                    schedule_id=schedule_id,
                    error=str(exc),
                )
                errors += 1

    logger.info("cron.evening_ping_complete", sent=sent, errors=errors)
    return {"sent": sent, "errors": errors}


# ── Legacy alias (kept for backwards compat with existing GH Actions) ─────────

@router.post("/daily-ping", status_code=status.HTTP_200_OK)
async def daily_ping(
    db: SupabaseDep,
    x_cron_secret: str = Header(alias="X-Cron-Secret"),
) -> dict:  # type: ignore[type-arg]
    """Alias for /cron/evening-ping — kept for backwards compatibility."""
    return await evening_ping(db=db, x_cron_secret=x_cron_secret)

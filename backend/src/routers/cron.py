"""Cron router – secured endpoints called by GitHub Actions.

Endpoints
---------
  POST /cron/morning-ping    – AI-personalised morning agenda per user
  POST /cron/evening-ping    – ONE consolidated check-in card per user (AI body)
  POST /cron/weekly-summary  – AI weekly insight message (run once a week)

All fire based on a 30-minute time window; pass ``?force=true`` to bypass.
"""

from __future__ import annotations

import zoneinfo
from datetime import date, datetime, time, timedelta

import structlog
from fastapi import APIRouter, Header, HTTPException, Query, status

from config import settings
from database import SupabaseDep
from services import ai_agent, whatsapp

router = APIRouter(prefix="/cron", tags=["cron"])
logger = structlog.get_logger(__name__)

WINDOW_MINUTES = 30


def _in_window(target: time, user_tz: str) -> bool:
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


# ── Morning ping ──────────────────────────────────────────────────────────────────────

@router.post("/morning-ping", status_code=status.HTTP_200_OK)
async def morning_ping(
    db: SupabaseDep,
    x_cron_secret: str = Header(alias="X-Cron-Secret"),
    force: bool = Query(default=False, description="Skip time-window check — useful for testing"),
) -> dict:  # type: ignore[type-arg]
    """Send each user an AI-generated morning motivation + agenda."""
    _guard(x_cron_secret)

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
        tz: str = user.get("timezone") or "Asia/Kolkata"
        personality: str = user.get("personality") or "analyst"
        user_name: str = user.get("name") or "there"
        user_morning: str = user.get("morning_time") or "08:00"

        # Check if it's the user's morning reminder time
        h, m = map(int, user_morning.split(":")[:2])
        if not (force or _in_window(time(h, m), tz)):
            continue

        try:
            tz_obj = zoneinfo.ZoneInfo(tz)
        except zoneinfo.ZoneInfoNotFoundError:
            tz_obj = zoneinfo.ZoneInfo("Asia/Kolkata")
        today_weekday = datetime.now(tz_obj).weekday()

        # Fetch ALL active tasks scheduled for today
        sched_res = (
            await db.table("schedules")
            .select("id, title, days_of_week")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .execute()
        )
        due = [
            s for s in (sched_res.data or [])
            if today_weekday in (s.get("days_of_week") or list(range(7)))
        ]
        if not due:
            continue

        # Fetch streak for personalisation
        streak_res = await db.table("streaks").select("current_streak").eq("user_id", user_id).limit(1).execute()
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
        except Exception as exc:
            logger.error("cron.morning_ping_failed", user_id=user_id, error=str(exc))
            errors += 1

    logger.info("cron.morning_ping_complete", sent=sent, errors=errors)
    return {"sent": sent, "errors": errors}


# ── Evening ping ──────────────────────────────────────────────────────────────────────

@router.post("/evening-ping", status_code=status.HTTP_200_OK)
async def evening_ping(
    db: SupabaseDep,
    x_cron_secret: str = Header(alias="X-Cron-Secret"),
    force: bool = Query(default=False, description="Skip time-window check — useful for testing"),
) -> dict:  # type: ignore[type-arg]
    """Send ONE consolidated AI-generated check-in card per user (all tasks in one message)."""
    _guard(x_cron_secret)

    today = date.today().isoformat()
    sent = errors = 0

    users_res = (
        await db.table("users")
        .select("id, phone_number, timezone, personality, name, evening_time")
        .eq("is_active", True)
        .execute()
    )

    for user in users_res.data or []:
        user_id: str = user["id"]
        phone: str = user["phone_number"]
        tz: str = user.get("timezone") or "Asia/Kolkata"
        personality: str = user.get("personality") or "analyst"
        user_name: str = user.get("name") or "there"
        user_evening: str = user.get("evening_time") or "21:00"

        # Check if it's the user's evening reminder time
        h, m = map(int, user_evening.split(":")[:2])
        if not (force or _in_window(time(h, m), tz)):
            continue

        try:
            tz_obj = zoneinfo.ZoneInfo(tz)
        except zoneinfo.ZoneInfoNotFoundError:
            tz_obj = zoneinfo.ZoneInfo("Asia/Kolkata")
        today_weekday = datetime.now(tz_obj).weekday()

        sched_res = (
            await db.table("schedules")
            .select("id, title, days_of_week")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .execute()
        )

        # Tasks due today that haven't been logged yet
        due: list[dict] = []
        for s in sched_res.data or []:
            days = s.get("days_of_week") or list(range(7))
            if today_weekday not in days:
                continue
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

        bal_res = await db.table("leave_balance").select("balance").eq("user_id", user_id).limit(1).execute()
        cl_balance = float(((bal_res.data or [{}])[0] or {}).get("balance", 3.0))

        streak_res = await db.table("streaks").select("current_streak").eq("user_id", user_id).limit(1).execute()
        streak = int(((streak_res.data or [{}])[0] or {}).get("current_streak", 0))

        try:
            # Deduplicate display titles (e.g. two "DSA + Python" → "DSA + Python (×2)")
            from collections import Counter
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
        except Exception as exc:
            logger.error("cron.evening_ping_failed", user_id=user_id, error=str(exc))
            errors += 1

    logger.info("cron.evening_ping_complete", sent=sent, errors=errors)
    return {"sent": sent, "errors": errors}


# ── Weekly summary ─────────────────────────────────────────────────────────────────

@router.post("/weekly-summary", status_code=status.HTTP_200_OK)
async def weekly_summary(
    db: SupabaseDep,
    x_cron_secret: str = Header(alias="X-Cron-Secret"),
) -> dict:  # type: ignore[type-arg]
    """Send each user an AI-generated weekly insight summary.  Run once a week."""
    _guard(x_cron_secret)

    week_ago = (date.today() - timedelta(days=6)).isoformat()
    today = date.today().isoformat()
    sent = errors = 0

    users_res = (
        await db.table("users")
        .select("id, phone_number, personality, name")
        .eq("is_active", True)
        .execute()
    )

    for user in users_res.data or []:
        user_id: str = user["id"]
        phone: str = user["phone_number"]
        personality: str = user.get("personality") or "analyst"
        user_name: str = user.get("name") or "there"

        logs_res = (
            await db.table("daily_logs")
            .select("completion_pct, log_date")
            .eq("user_id", user_id)
            .gte("log_date", week_ago)
            .lte("log_date", today)
            .execute()
        )
        logs = logs_res.data or []

        streak_res = await db.table("streaks").select("current_streak, all_time_high").eq("user_id", user_id).limit(1).execute()
        streak_row = (streak_res.data or [{}])[0] or {}
        streak = int(streak_row.get("current_streak", 0))
        all_time_high = int(streak_row.get("all_time_high", 0))

        try:
            msg = await ai_agent.generate_weekly_summary(
                user_name=user_name,
                streak=streak,
                all_time_high=all_time_high,
                logs=logs,
                personality=personality,
            )
            await whatsapp.send_text_message(phone, msg)
            sent += 1
        except Exception as exc:
            logger.error("cron.weekly_summary_failed", user_id=user_id, error=str(exc))
            errors += 1

    logger.info("cron.weekly_summary_complete", sent=sent, errors=errors)
    return {"sent": sent, "errors": errors}


# ── Legacy alias ────────────────────────────────────────────────────────────────────

@router.post("/daily-ping", status_code=status.HTTP_200_OK)
async def daily_ping(
    db: SupabaseDep,
    x_cron_secret: str = Header(alias="X-Cron-Secret"),
) -> dict:  # type: ignore[type-arg]
    """Alias for /cron/evening-ping — kept for backwards compatibility."""
    return await evening_ping(db=db, x_cron_secret=x_cron_secret)

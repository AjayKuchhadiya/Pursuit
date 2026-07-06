"""Gamification engine.

All rules live here so they are easy to unit-test independently of HTTP
or database concerns.  Each public function receives primitive data and
returns a ``GameResult`` dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import structlog
from supabase._async.client import AsyncClient

logger = structlog.get_logger(__name__)

# A streak day counts as "complete" when completion ≥ this threshold.
COMPLETION_THRESHOLD = 80

# Number of consecutive complete days that earns a CL bonus.
STREAK_BONUS_INTERVAL = 7

# CL tokens awarded at each bonus interval.
CL_BONUS_AMOUNT = 1.0


@dataclass
class GameResult:
    current_streak: int
    all_time_high: int
    cl_balance: float
    streak_saved_by_cl: bool = False
    cl_earned: bool = False
    unlocked_rewards: list[dict] = field(default_factory=list)  # type: ignore[type-arg]


async def process_log(
    db: AsyncClient,
    user_id: str,
    schedule_id: str,
    log_date: date,
    completion_pct: int,
    is_casual_leave: bool,
) -> GameResult:
    """Core gamification logic triggered after every check-in response.

    Steps
    -----
    1. Insert the daily log row.
    2. Apply CL / streak / reset rules.
    3. Update ``streaks`` and ``leave_balance`` tables.
    4. Check reward milestones.
    5. Return :class:`GameResult`.
    """
    # ── 1. Upsert log (update if already logged today) ───────────────────────
    await db.table("daily_logs").upsert(
        {
            "user_id": user_id,
            "schedule_id": schedule_id,
            "log_date": log_date.isoformat(),
            "completion_pct": completion_pct,
            "is_casual_leave": is_casual_leave,
        },
        on_conflict="user_id,schedule_id,log_date",
    ).execute()

    # ── 2. Fetch current streak & CL balance ──────────────────────────────────
    _streak_res = await db.table("streaks").select("*").eq("user_id", user_id).limit(1).execute()
    streak_row = (_streak_res.data or [{}])[0] or {"current_streak": 0, "all_time_high": 0, "last_active_date": None}

    _bal_res = (
        await db.table("leave_balance")
        .select("balance")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    balance_row = (_bal_res.data or [{}])[0] or {"balance": 3.0}

    current_streak: int = streak_row["current_streak"]
    all_time_high: int = streak_row["all_time_high"]
    cl_balance: float = float(balance_row["balance"])

    streak_saved_by_cl = False
    cl_earned = False

    # Streak should only change once per day — skip gamification if already processed today
    already_today = streak_row.get("last_active_date") == log_date.isoformat()
    if already_today:
        return GameResult(
            current_streak=current_streak,
            all_time_high=all_time_high,
            cl_balance=cl_balance,
        )

    # ── 3. Apply rules ────────────────────────────────────────────────────────
    if is_casual_leave:
        if cl_balance < 1.0:
            # Not enough leaves – treat as missed (caller should have validated)
            current_streak = 0
        else:
            cl_balance -= 1.0
            streak_saved_by_cl = True
            # streak is frozen – no increment, no reset
    elif completion_pct >= COMPLETION_THRESHOLD:
        current_streak += 1
        # 7-day streak bonus
        if current_streak % STREAK_BONUS_INTERVAL == 0:
            cl_balance += CL_BONUS_AMOUNT
            cl_earned = True
            logger.info("gamification.cl_bonus_awarded", user_id=user_id, streak=current_streak)
    else:
        current_streak = 0

    all_time_high = max(all_time_high, current_streak)

    # ── 4. Persist streak & balance ───────────────────────────────────────────
    await db.table("streaks").upsert(
        {
            "user_id": user_id,
            "current_streak": current_streak,
            "all_time_high": all_time_high,
            "last_active_date": log_date.isoformat(),
        }
    ).execute()

    await db.table("leave_balance").upsert(
        {"user_id": user_id, "balance": cl_balance}
    ).execute()

    # ── 5. Check reward milestones ────────────────────────────────────────────
    unlocked = await _check_rewards(db, user_id, current_streak, cl_balance)

    logger.info(
        "gamification.processed",
        user_id=user_id,
        streak=current_streak,
        cl_balance=cl_balance,
    )
    return GameResult(
        current_streak=current_streak,
        all_time_high=all_time_high,
        cl_balance=cl_balance,
        streak_saved_by_cl=streak_saved_by_cl,
        cl_earned=cl_earned,
        unlocked_rewards=unlocked,
    )


async def _check_rewards(
    db: AsyncClient,
    user_id: str,
    current_streak: int,
    cl_balance: float,
) -> list[dict]:  # type: ignore[type-arg]
    """Unlock any rewards whose conditions are now satisfied."""
    result = (
        await db.table("rewards")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_unlocked", False)
        .execute()
    )
    rewards = result.data or []
    newly_unlocked = []

    for reward in rewards:
        ctype = reward["condition_type"]
        cval = float(reward["condition_value"])
        unlocked = False

        if ctype == "streak_days" and current_streak >= cval:
            unlocked = True
        # weekly_avg_pct and total_days can be added when the logs query is available

        if unlocked:
            await db.table("rewards").update({"is_unlocked": True}).eq("id", reward["id"]).execute()
            newly_unlocked.append(reward)
            logger.info("gamification.reward_unlocked", reward_id=reward["id"], user_id=user_id)

    return newly_unlocked


async def get_weekly_avg(db: AsyncClient, user_id: str) -> float:
    """Return the average completion_pct for the last 7 days (0–100)."""
    from datetime import timedelta

    today = date.today()
    week_ago = (today - timedelta(days=6)).isoformat()
    result = (
        await db.table("daily_logs")
        .select("completion_pct")
        .eq("user_id", user_id)
        .eq("is_casual_leave", False)
        .gte("log_date", week_ago)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return 0.0
    return sum(r["completion_pct"] for r in rows) / len(rows)

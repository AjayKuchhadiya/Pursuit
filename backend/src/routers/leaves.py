"""Skip Day router."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from database import SupabaseDep
from dependencies import CurrentUser
from services import gamification

router = APIRouter(prefix="/leaves", tags=["leaves"])
logger = structlog.get_logger(__name__)


class ApplyLeaveBody(BaseModel):
    log_date: Optional[date] = None  # defaults to today if omitted


@router.get("")
async def get_leave_balance(db: SupabaseDep, user: CurrentUser) -> dict:  # type: ignore[type-arg]
    res = (
        await db.table("leave_balance")
        .select("balance")
        .eq("user_id", user["id"])
        .limit(1)
        .execute()
    )
    balance = float(((res.data or [{}])[0] or {}).get("balance", 3.0))
    return {"balance": balance}


@router.post("/apply", status_code=status.HTTP_200_OK)
async def apply_casual_leave(body: ApplyLeaveBody, db: SupabaseDep, user: CurrentUser) -> dict:  # type: ignore[type-arg]
    """Apply a Skip Day for the given date (defaults to today) from the dashboard."""
    user_id: str = user["id"]

    target_date = body.log_date or date.today()

    # Guard: only one log per day
    existing = (
        await db.table("daily_logs")
        .select("id")
        .eq("user_id", user_id)
        .eq("log_date", target_date.isoformat())
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A log for {target_date.isoformat()} already exists.",
        )

    # Fetch active schedule
    sched_res = (
        await db.table("schedules")
        .select("id")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not sched_res.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active schedule found.",
        )

    bal_res = (
        await db.table("leave_balance")
        .select("balance")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    balance = float(((bal_res.data or [{}])[0] or {}).get("balance", 0.0))
    if balance < 1.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient Skip Day balance.",
        )

    result = await gamification.process_log(
        db=db,
        user_id=user_id,
        schedule_id=sched_res.data[0]["id"],
        log_date=target_date,
        completion_pct=0,
        is_casual_leave=True,
    )
    return {
        "detail": f"Skip Day applied for {target_date.isoformat()}. Your streak is protected! 🛋️",
        "cl_balance": result.cl_balance,
        "current_streak": result.current_streak,
    }

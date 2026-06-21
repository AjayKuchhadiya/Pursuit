"""Users router – profile and streak/dashboard data."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from database import SupabaseDep
from dependencies import CurrentUser
from schemas.user import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])
logger = structlog.get_logger(__name__)


@router.get("/me", response_model=UserRead)
async def get_me(user: CurrentUser) -> UserRead:
    return UserRead(**user)


@router.patch("/me", response_model=UserRead)
async def update_me(body: UserUpdate, db: SupabaseDep, user: CurrentUser) -> UserRead:
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return UserRead(**user)
    res = (
        await db.table("users")
        .update(updates)
        .eq("id", user["id"])
        .select("*")
        .execute()
    )
    return UserRead(**res.data[0])


@router.get("/me/stats")
async def get_stats(db: SupabaseDep, user: CurrentUser) -> dict:  # type: ignore[type-arg]
    """Return streak info and CL balance for the dashboard header."""
    streak_res = (
        await db.table("streaks")
        .select("current_streak, all_time_high")
        .eq("user_id", user["id"])
        .maybe_single()
        .execute()
    )
    bal_res = (
        await db.table("leave_balance")
        .select("balance")
        .eq("user_id", user["id"])
        .maybe_single()
        .execute()
    )
    return {
        "current_streak": (streak_res.data or {}).get("current_streak", 0),
        "all_time_high": (streak_res.data or {}).get("all_time_high", 0),
        "cl_balance": float((bal_res.data or {}).get("balance", 3.0)),
    }

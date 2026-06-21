"""Rewards router."""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, status

from database import SupabaseDep
from dependencies import CurrentUser
from schemas.reward import RewardCreate, RewardRead

router = APIRouter(prefix="/rewards", tags=["rewards"])
logger = structlog.get_logger(__name__)


@router.get("", response_model=list[RewardRead])
async def list_rewards(db: SupabaseDep, user: CurrentUser) -> list[RewardRead]:
    res = await db.table("rewards").select("*").eq("user_id", user["id"]).execute()
    return [RewardRead(**row) for row in (res.data or [])]


@router.post("", response_model=RewardRead, status_code=status.HTTP_201_CREATED)
async def create_reward(body: RewardCreate, db: SupabaseDep, user: CurrentUser) -> RewardRead:
    res = (
        await db.table("rewards")
        .insert(
            {
                "user_id": user["id"],
                "title": body.title,
                "condition_type": body.condition_type,
                "condition_value": body.condition_value,
                "is_unlocked": False,
            }
        )
        .select("*")
        .execute()
    )
    return RewardRead(**res.data[0])

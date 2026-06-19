"""Reward schemas."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class ConditionType(StrEnum):
    STREAK_DAYS = "streak_days"
    WEEKLY_AVG_PCT = "weekly_avg_pct"
    TOTAL_DAYS = "total_days"


class RewardCreate(BaseModel):
    title: str
    condition_type: ConditionType
    condition_value: float


class RewardRead(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    condition_type: ConditionType
    condition_value: float
    is_unlocked: bool

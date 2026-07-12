"""Schedule schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

# 0=Monday, 1=Tuesday, ..., 6=Sunday  (matches Python datetime.weekday())
_ALL_DAYS = [0, 1, 2, 3, 4, 5, 6]


class ScheduleCreate(BaseModel):
    title: str
    is_active: bool = True
    days_of_week: list[int] = _ALL_DAYS
    duration_minutes: int = 60  # how long the user plans to spend on this goal each day


class ScheduleUpdate(BaseModel):
    title: str | None = None
    is_active: bool | None = None
    days_of_week: list[int] | None = None
    duration_minutes: int | None = None
    status: Literal["active", "paused", "completed"] | None = None


class ScheduleRead(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    is_active: bool
    days_of_week: list[int]
    duration_minutes: int
    status: str = "active"
    completed_at: datetime | None = None
    created_at: datetime
    total_checkins: int = 0

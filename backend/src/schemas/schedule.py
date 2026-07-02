"""Schedule schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

# 0=Monday, 1=Tuesday, ..., 6=Sunday  (matches Python datetime.weekday())
_ALL_DAYS = [0, 1, 2, 3, 4, 5, 6]


class ScheduleCreate(BaseModel):
    title: str
    is_active: bool = True
    morning_time: str = "08:00"   # HH:MM 24h in user's local timezone
    evening_time: str = "21:00"   # HH:MM 24h in user's local timezone
    days_of_week: list[int] = _ALL_DAYS  # which days this schedule is active


class ScheduleUpdate(BaseModel):
    title: str | None = None
    is_active: bool | None = None
    morning_time: str | None = None
    evening_time: str | None = None
    days_of_week: list[int] | None = None


class ScheduleRead(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    is_active: bool
    morning_time: str
    evening_time: str
    days_of_week: list[int]

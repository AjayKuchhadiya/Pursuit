"""Schedule schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class ScheduleCreate(BaseModel):
    title: str
    is_active: bool = True
    morning_time: str = "08:00"   # HH:MM 24h in user's local timezone
    evening_time: str = "21:00"   # HH:MM 24h in user's local timezone


class ScheduleUpdate(BaseModel):
    title: str | None = None
    is_active: bool | None = None
    morning_time: str | None = None
    evening_time: str | None = None


class ScheduleRead(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    is_active: bool
    morning_time: str
    evening_time: str

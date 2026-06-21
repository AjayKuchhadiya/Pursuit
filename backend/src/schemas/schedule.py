"""Schedule schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class ScheduleCreate(BaseModel):
    title: str
    is_active: bool = True


class ScheduleUpdate(BaseModel):
    title: str | None = None
    is_active: bool | None = None


class ScheduleRead(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    is_active: bool

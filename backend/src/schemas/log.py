"""Daily-log schemas."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, field_validator


class LogCreate(BaseModel):
    schedule_id: UUID
    log_date: date
    completion_pct: int
    is_casual_leave: bool = False

    @field_validator("completion_pct")
    @classmethod
    def _clamp(cls, v: int) -> int:
        if not (0 <= v <= 100):
            raise ValueError("completion_pct must be between 0 and 100")
        return v


class LogRead(BaseModel):
    id: UUID
    user_id: UUID
    schedule_id: UUID
    log_date: date
    completion_pct: int
    is_casual_leave: bool


class HeatmapEntry(BaseModel):
    date: date
    value: int          # 0 | 50 | 100
    entry_type: str     # "done" | "partial" | "casual_leave" | "missed"

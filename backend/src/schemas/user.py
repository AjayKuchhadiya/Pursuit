"""User schemas."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, field_validator


class Personality(StrEnum):
    CHEERLEADER = "cheerleader"
    DRILL_SERGEANT = "drill_sergeant"
    ANALYST = "analyst"


class UserUpdate(BaseModel):
    personality: Personality | None = None
    timezone: str | None = None
    name: str | None = None
    morning_time: str | None = None  # HH:MM 24h in user's local timezone
    evening_time: str | None = None  # HH:MM 24h in user's local timezone

    @field_validator("timezone")
    @classmethod
    def _validate_tz(cls, v: str | None) -> str | None:
        if v is None:
            return v
        import zoneinfo

        try:
            zoneinfo.ZoneInfo(v)
        except zoneinfo.ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {v!r}") from exc
        return v


class UserRead(BaseModel):
    id: UUID
    phone_number: str
    name: str
    personality: Personality
    timezone: str
    morning_time: str = "08:00"
    evening_time: str = "21:00"
    is_active: bool

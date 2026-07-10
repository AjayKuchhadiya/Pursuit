"""Logs router – daily log history and heatmap data."""

from __future__ import annotations

from datetime import date

import structlog
from fastapi import APIRouter, Query

from database import SupabaseDep
from dependencies import CurrentUser
from schemas.log import HeatmapEntry, LogRead

router = APIRouter(prefix="/logs", tags=["logs"])
logger = structlog.get_logger(__name__)


@router.get("", response_model=list[LogRead])
async def get_logs(
    db: SupabaseDep,
    user: CurrentUser,
    start: date = Query(default=None),
    end: date = Query(default=None),
) -> list[LogRead]:
    query = db.table("daily_logs").select("*").eq("user_id", user["id"])
    if start:
        query = query.gte("log_date", start.isoformat())
    if end:
        query = query.lte("log_date", end.isoformat())
    res = await query.order("log_date", desc=True).execute()
    return [LogRead(**row) for row in (res.data or [])]


@router.get("/heatmap", response_model=list[HeatmapEntry])
async def get_heatmap(
    db: SupabaseDep,
    user: CurrentUser,
    start: date = Query(default=None),
    end: date = Query(default=None),
) -> list[HeatmapEntry]:
    """Return log data formatted for the GitHub-style contribution heatmap.

    When a user has multiple active schedules, multiple logs exist per day.
    Aggregate them into one entry per day: a day is "done" only if every
    schedule hit the completion threshold; a casual-leave on any schedule
    marks the whole day as casual_leave.
    """
    query = db.table("daily_logs").select("*").eq("user_id", user["id"])
    if start:
        query = query.gte("log_date", start.isoformat())
    if end:
        query = query.lte("log_date", end.isoformat())
    res = await query.order("log_date").execute()

    # Group rows by date, then take the worst-case across schedules.
    from collections import defaultdict
    by_date: dict = defaultdict(list)
    for row in res.data or []:
        by_date[row["log_date"]].append(row)

    entries = []
    for log_date in sorted(by_date):
        rows = by_date[log_date]
        # Any casual-leave makes the whole day casual_leave
        if any(r["is_casual_leave"] for r in rows):
            entry_type = "casual_leave"
            value = 0
        else:
            # Use the minimum completion across all schedules for the day
            value = min(r["completion_pct"] for r in rows)
            if value >= 80:
                entry_type = "done"
            elif value > 0:
                entry_type = "partial"
            else:
                entry_type = "missed"

        entries.append(HeatmapEntry(date=log_date, value=value, entry_type=entry_type))
    return entries

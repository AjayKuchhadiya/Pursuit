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
    """Return log data formatted for the GitHub-style contribution heatmap."""
    query = db.table("daily_logs").select("*").eq("user_id", user["id"])
    if start:
        query = query.gte("log_date", start.isoformat())
    if end:
        query = query.lte("log_date", end.isoformat())
    res = await query.order("log_date").execute()

    entries = []
    for row in res.data or []:
        if row["is_casual_leave"]:
            entry_type = "casual_leave"
        elif row["completion_pct"] >= 80:
            entry_type = "done"
        elif row["completion_pct"] > 0:
            entry_type = "partial"
        else:
            entry_type = "missed"

        entries.append(
            HeatmapEntry(
                date=row["log_date"],
                value=row["completion_pct"],
                entry_type=entry_type,
            )
        )
    return entries

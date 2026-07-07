"""Health-check router.

/health     – confirm the server is up (no auth, no DB)
/health/db  – ping the database to keep Supabase from auto-pausing
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, status

from database import SupabaseDep

router = APIRouter(tags=["health"])
logger = structlog.get_logger(__name__)


@router.get("/health")
async def health() -> dict:  # type: ignore[type-arg]
    """Simple liveness check — returns immediately with no I/O."""
    return {"status": "healthy"}


@router.get("/health/db")
async def health_db(db: SupabaseDep) -> dict:  # type: ignore[type-arg]
    """Readiness check — runs a lightweight query to keep the Supabase instance awake."""
    try:
        await db.table("users").select("id").limit(1).execute()
    except Exception as exc:
        logger.error("health.db_check_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unreachable",
        ) from exc
    return {"status": "db_alive"}

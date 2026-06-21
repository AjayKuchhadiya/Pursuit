"""Cron router – secured daily-ping endpoint called by GitHub Actions."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Header, HTTPException, status

from config import settings
from database import SupabaseDep
from services import whatsapp

router = APIRouter(prefix="/cron", tags=["cron"])
logger = structlog.get_logger(__name__)


@router.post("/daily-ping", status_code=status.HTTP_200_OK)
async def daily_ping(
    db: SupabaseDep,
    x_cron_secret: str = Header(alias="X-Cron-Secret"),
) -> dict:  # type: ignore[type-arg]
    """Fan out daily check-in messages to all active users.

    Protected by the ``X-Cron-Secret`` header.  Set this value in
    ``CRON_SECRET`` env var and as a GitHub Actions repository secret.
    """
    if x_cron_secret != settings.cron_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # Fetch all active users who have at least one active schedule
    users_res = await db.table("users").select("id, phone_number, personality").eq("is_active", True).execute()
    users = users_res.data or []

    sent = 0
    errors = 0

    for user in users:
        user_id: str = user["id"]
        phone: str = user["phone_number"]

        sched_res = (
            await db.table("schedules")
            .select("id, title")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if not sched_res.data:
            continue

        schedule = sched_res.data[0]

        bal_res = (
            await db.table("leave_balance")
            .select("balance")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        cl_balance = float(((bal_res.data or [{}])[0] or {}).get("balance", 3.0))

        try:
            await whatsapp.send_interactive_checkin(
                phone=phone,
                schedule_title=schedule["title"],
                cl_balance=cl_balance,
            )
            sent += 1
        except Exception as exc:
            logger.error("cron.ping_failed", user_id=user_id, error=str(exc))
            errors += 1

    logger.info("cron.daily_ping_complete", sent=sent, errors=errors)
    return {"sent": sent, "errors": errors}

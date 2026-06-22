"""Meta WhatsApp webhook router.

GET  /webhook  – Meta verification challenge
POST /webhook  – Incoming button-tap events → gamification → reply
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from config import settings
from database import SupabaseDep
from services import bot_personality, gamification, whatsapp

router = APIRouter(prefix="/webhook", tags=["webhook"])
logger = structlog.get_logger(__name__)


# ── GET: Meta verification handshake ─────────────────────────────────────────

@router.get("")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> str:
    if hub_mode != "subscribe" or hub_verify_token != settings.meta_webhook_verify_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return hub_challenge


# ── Swagger-friendly test body ────────────────────────────────────────────────

class WebhookPayload(BaseModel):
    """
    Mirrors Meta's webhook payload structure.

    **Quick test in Swagger – paste one of these:**

    Tap Done (100%):
    ```json
    {"entry":[{"changes":[{"value":{"messages":[{"from":"+917457878864","type":"interactive","interactive":{"button_reply":{"id":"log_100"}}}]}}]}]}
    ```
    Tap Halfway (50%):
    ```json
    {"entry":[{"changes":[{"value":{"messages":[{"from":"+917457878864","type":"interactive","interactive":{"button_reply":{"id":"log_50"}}}]}}]}]}
    ```
    Apply Casual Leave:
    ```json
    {"entry":[{"changes":[{"value":{"messages":[{"from":"+917457878864","type":"interactive","interactive":{"button_reply":{"id":"apply_cl"}}}]}}]}]}
    ```
    """
    entry: list[Any]


# ── POST: Incoming messages ───────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_200_OK)
async def receive_webhook(body: WebhookPayload, db: SupabaseDep) -> dict:  # type: ignore[type-arg]
    """Parse Meta's webhook payload and process interactive button replies."""
    try:
        payload = body.model_dump()
    except Exception:
        return {"status": "ignored"}

    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]["value"]
        message = change["messages"][0]
        phone = message["from"]
        msg_type = message.get("type")
    except (KeyError, IndexError):
        # Not a message event (e.g. status update) – ack and ignore
        return {"status": "ignored"}

    if msg_type != "interactive":
        logger.info("webhook.non_interactive", type=msg_type, from_=phone)
        return {"status": "ignored"}

    button_id: str = message["interactive"]["button_reply"]["id"]
    logger.info("webhook.button_tap", button_id=button_id, from_=phone)

    # Button ID format: "<action>:<schedule_id>"  e.g. "log_100:abc-uuid"
    # Also accept legacy format without schedule_id for Swagger testing
    parts = button_id.split(":", 1)
    action = parts[0]
    schedule_id_from_button: str | None = parts[1] if len(parts) == 2 else None

    if action == whatsapp.BUTTON_ID_DONE:
        completion_pct, is_cl = 100, False
    elif action == whatsapp.BUTTON_ID_HALFWAY:
        completion_pct, is_cl = 50, False
    elif action == whatsapp.BUTTON_ID_CASUAL_LEAVE:
        completion_pct, is_cl = 0, True
    else:
        logger.warning("webhook.unknown_button", button_id=button_id)
        return {"status": "ignored"}

    # Fetch user
    user_res = (
        await db.table("users")
        .select("id, personality")
        .eq("phone_number", phone)
        .limit(1)
        .execute()
    )
    if not user_res.data:
        logger.warning("webhook.unknown_phone", phone=phone)
        await whatsapp.send_text_message(
            phone,
            "Hi! You don't have a Pursuit account yet. Please sign up at the dashboard.",
        )
        return {"status": "unregistered"}

    user = user_res.data[0]
    user_id: str = user["id"]
    personality: str = user["personality"]

    # Resolve schedule_id: prefer the one encoded in the button, else fallback to first active
    if schedule_id_from_button:
        sched_res = (
            await db.table("schedules")
            .select("id")
            .eq("id", schedule_id_from_button)
            .eq("user_id", user_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
    else:
        sched_res = (
            await db.table("schedules")
            .select("id")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )

    if not sched_res.data:
        await whatsapp.send_text_message(
            phone,
            "You don't have an active schedule. Create one from the Pursuit dashboard first!",
        )
        return {"status": "no_schedule"}

    schedule_id: str = sched_res.data[0]["id"]

    from datetime import date

    # Validate CL balance before processing
    if is_cl:
        bal_res = (
            await db.table("leave_balance")
            .select("balance")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        balance = float(((bal_res.data or [{}])[0] or {}).get("balance", 0.0))
        if balance < 1.0:
            await whatsapp.send_text_message(
                phone,
                "❌ You don't have any Casual Leaves left! Earn more by completing 7-day streaks.",
            )
            return {"status": "no_cl_balance"}

    result = await gamification.process_log(
        db=db,
        user_id=user_id,
        schedule_id=schedule_id,
        log_date=date.today(),
        completion_pct=completion_pct,
        is_casual_leave=is_cl,
    )

    reply = bot_personality.get_response_message(personality, completion_pct, result)
    await whatsapp.send_text_message(phone, reply)

    return {"status": "processed"}

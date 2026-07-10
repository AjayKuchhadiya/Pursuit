"""Meta WhatsApp webhook router.

GET  /webhook  – Meta verification challenge
POST /webhook  – Incoming button-tap events → gamification → reply
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from config import settings
from database import SupabaseDep
from services import ai_agent, bot_personality, gamification, whatsapp

router = APIRouter(prefix="/webhook", tags=["webhook"])
logger = structlog.get_logger(__name__)


# ── GET: Meta verification handshake ─────────────────────────────────────────

@router.get("", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> PlainTextResponse:
    if hub_mode != "subscribe" or hub_verify_token != settings.meta_webhook_verify_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return PlainTextResponse(content=hub_challenge)


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
    Apply Skip Day:
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
        return await _process_webhook(body, db)
    except Exception as exc:
        logger.error(
            "webhook.unhandled_error",
            error=str(exc),
            traceback=__import__("traceback").format_exc(),
        )
        raise


async def _process_webhook(body: WebhookPayload, db: SupabaseDep) -> dict:  # type: ignore[type-arg]
    try:
        payload = body.model_dump()
    except Exception:
        return {"status": "ignored"}

    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]["value"]
        message = change["messages"][0]
        phone = message["from"]
        # Meta omits the leading '+' — normalise to E.164 for DB lookup
        if not phone.startswith("+"):
            phone = "+" + phone
        msg_type = message.get("type")
    except (KeyError, IndexError):
        # Not a message event (e.g. status update) – ack and ignore
        return {"status": "ignored"}

    if msg_type != "interactive" and msg_type != "text":
        logger.info("webhook.non_interactive", type=msg_type, from_=phone)
        return {"status": "ignored"}

    # ── Text reply → AI parse & log all schedules ────────────────────────────
    if msg_type == "text":
        return await _process_text_checkin(phone, message["text"]["body"], db)

    # ── Interactive button tap ────────────────────────────────────────────────

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
    elif action == "log_0":  # "Missed" button on the consolidated evening card
        completion_pct, is_cl = 0, False
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

    # Resolve schedule_id: handle ':all' consolidated buttons
    from datetime import date as _date
    today = _date.today().isoformat()

    if schedule_id_from_button == "all" or action == "log_0":
        # Consolidated card: get ALL active schedules for this user
        sched_res = (
            await db.table("schedules")
            .select("id, title")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .execute()
        )
        if not sched_res.data:
            await whatsapp.send_text_message(
                phone,
                "You don't have an active schedule. Create one from the Pursuit dashboard first!",
            )
            return {"status": "no_schedule"}

        # Log each schedule and process gamification (guard inside prevents double-incrementing)
        results = []
        last_result = None
        for sched in sched_res.data:
            if is_cl:
                bal_res = await db.table("leave_balance").select("balance").eq("user_id", user_id).limit(1).execute()
                if float(((bal_res.data or [{}])[0] or {}).get("balance", 0.0)) < 1.0:
                    await whatsapp.send_text_message(phone, "❌ You don't have any Skip Days left!")
                    return {"status": "no_cl_balance"}
            try:
                last_result = await gamification.process_log(
                    db=db, user_id=user_id, schedule_id=sched["id"],
                    log_date=_date.today(), completion_pct=completion_pct, is_casual_leave=is_cl,
                )
                results.append({"schedule_title": sched["title"], "completion_pct": completion_pct})
            except Exception as exc:
                logger.error("webhook.button_log_failed", schedule_id=sched["id"], error=str(exc))

        if last_result is None:
            await whatsapp.send_text_message(
                phone,
                "⚠️ Something went wrong logging your check-in. Please try again or use the dashboard.",
            )
            return {"status": "log_failed"}

        user_name_res = await db.table("users").select("name").eq("id", user_id).limit(1).execute()
        user_name = ((user_name_res.data or [{}])[0] or {}).get("name") or "there"

        reply = await ai_agent.generate_checkin_reply(
            user_name=user_name,
            streak=last_result.current_streak,
            results=results,
            personality=personality,
            cl_balance=last_result.cl_balance,
            streak_saved=last_result.streak_saved_by_cl,
            cl_earned=last_result.cl_earned,
        )
        await whatsapp.send_text_message(phone, reply)
        return {"status": "processed"}

    # ── Single-schedule path (legacy Swagger test / specific schedule button) ──
    if schedule_id_from_button:
        sched_res = (
            await db.table("schedules").select("id, title")
            .eq("id", schedule_id_from_button).eq("user_id", user_id).eq("is_active", True)
            .limit(1).execute()
        )
    else:
        sched_res = (
            await db.table("schedules").select("id, title")
            .eq("user_id", user_id).eq("is_active", True).limit(1).execute()
        )

    if not sched_res.data:
        await whatsapp.send_text_message(phone, "No active schedule found. Create one in the dashboard!")
        return {"status": "no_schedule"}

    sched = sched_res.data[0]

    if is_cl:
        bal_res = await db.table("leave_balance").select("balance").eq("user_id", user_id).limit(1).execute()
        if float(((bal_res.data or [{}])[0] or {}).get("balance", 0.0)) < 1.0:
            await whatsapp.send_text_message(phone, "❌ You don't have any Skip Days left!")
            return {"status": "no_cl_balance"}

    from datetime import date as _date2
    try:
        result = await gamification.process_log(
            db=db, user_id=user_id, schedule_id=sched["id"],
            log_date=_date2.today(), completion_pct=completion_pct, is_casual_leave=is_cl,
        )
    except Exception as exc:
        logger.error("webhook.button_log_failed", schedule_id=sched["id"], error=str(exc))
        await whatsapp.send_text_message(
            phone,
            "⚠️ Something went wrong logging your check-in. Please try again or use the dashboard.",
        )
        return {"status": "log_failed"}

    user_name_res = await db.table("users").select("name").eq("id", user_id).limit(1).execute()
    user_name = ((user_name_res.data or [{}])[0] or {}).get("name") or "there"

    reply = await ai_agent.generate_checkin_reply(
        user_name=user_name,
        streak=result.current_streak,
        results=[{"schedule_title": sched["title"], "completion_pct": completion_pct}],
        personality=personality,
        cl_balance=result.cl_balance,
        streak_saved=result.streak_saved_by_cl,
        cl_earned=result.cl_earned,
    )
    await whatsapp.send_text_message(phone, reply)
    return {"status": "processed"}


# ── Text reply handler ─────────────────────────────────────────────────────────

async def _process_text_checkin(phone: str, text: str, db: SupabaseDep) -> dict:  # type: ignore[type-arg]
    """Parse a free-text WhatsApp reply via AI and log per-schedule completions."""
    user_res = (
        await db.table("users").select("id, personality, name")
        .eq("phone_number", phone).limit(1).execute()
    )
    if not user_res.data:
        await whatsapp.send_text_message(
            phone, "Hi! You don't have a Pursuit account yet. Sign up at the dashboard."
        )
        return {"status": "unregistered"}

    user = user_res.data[0]
    user_id: str = user["id"]
    personality: str = user["personality"]
    user_name: str = user.get("name") or "there"

    sched_res = (
        await db.table("schedules").select("id, title")
        .eq("user_id", user_id).eq("is_active", True).execute()
    )
    schedules = sched_res.data or []
    if not schedules:
        await whatsapp.send_text_message(phone, "No active schedules found. Add one in the dashboard!")
        return {"status": "no_schedule"}

    logger.info("webhook.text_checkin", from_=phone, text_length=len(text))

    # ── Classify intent before treating as a check-in ────────────────────────
    intent = await ai_agent.classify_message(text)

    if intent == "query":
        streak_res = await db.table("streaks").select("current_streak").eq("user_id", user_id).limit(1).execute()
        streak = int(((streak_res.data or [{}])[0] or {}).get("current_streak", 0))
        reply = await ai_agent.generate_query_reply(
            user_text=text,
            user_name=user_name,
            streak=streak,
            schedules=[s["title"] for s in schedules],
            personality=personality,
        )
        await whatsapp.send_text_message(phone, reply)
        return {"status": "query_answered"}

    if intent == "other":
        await whatsapp.send_text_message(
            phone,
            f"Hey {user_name}! 👋 Send me your check-in update or tap the buttons from your evening ping.",
        )
        return {"status": "non_checkin"}

    # intent == "checkin" → parse and log
    parsed = await ai_agent.parse_checkin(
        user_text=text, schedules=schedules, user_name=user_name
    )

    from datetime import date as _date3
    results = []
    last_result = None
    for item in parsed:
        try:
            last_result = await gamification.process_log(
                db=db, user_id=user_id, schedule_id=item["schedule_id"],
                log_date=_date3.today(), completion_pct=item["completion_pct"], is_casual_leave=False,
            )
            results.append({"schedule_title": item["schedule_title"], "completion_pct": item["completion_pct"]})
        except Exception as exc:
            logger.error("webhook.text_log_failed", schedule_id=item.get("schedule_id"), error=str(exc))

    if last_result is None:
        await whatsapp.send_text_message(phone, "Got it! But I couldn't log anything — try again?")
        return {"status": "log_failed"}

    reply = await ai_agent.generate_checkin_reply(
        user_name=user_name,
        streak=last_result.current_streak,
        results=results,
        personality=personality,
        cl_balance=last_result.cl_balance,
        streak_saved=last_result.streak_saved_by_cl,
        cl_earned=last_result.cl_earned,
    )
    await whatsapp.send_text_message(phone, reply)
    return {"status": "processed"}

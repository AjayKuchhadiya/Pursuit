"""Meta WhatsApp Business Cloud API client.

All outbound calls are made with an async ``httpx.AsyncClient`` so they
don't block the FastAPI event loop.
"""

from __future__ import annotations

import httpx
import structlog

from config import settings

logger = structlog.get_logger(__name__)

# Stable button-reply IDs – keep in sync with webhook parser
BUTTON_ID_DONE = "log_100"
BUTTON_ID_HALFWAY = "log_50"
BUTTON_ID_CASUAL_LEAVE = "apply_cl"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.meta_access_token}",
        "Content-Type": "application/json",
    }


async def send_text_message(phone: str, body: str) -> None:
    """Send a plain-text WhatsApp message to *phone* (E.164 format)."""
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": body},
    }
    url = f"{settings.meta_api_base_url}/{settings.meta_phone_number_id}/messages"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload, headers=_headers())
        resp.raise_for_status()
    logger.info("whatsapp.text_sent", to=phone)


async def send_otp_message(phone: str, otp: str) -> None:
    """Send the OTP code as a plain-text WhatsApp message.

    NOTE: Free-form messages only deliver within the 24-hour conversation
    window (Meta test account limitation).  Once the business is verified
    and a real WABA is connected, switch this to an authentication template
    to remove the window restriction.
    """
    body = (
        f"\U0001f510 Your Pursuit verification code is: *{otp}*\n\n"
        "This code expires in 10 minutes. Do not share it with anyone."
    )
    await send_text_message(phone, body)


async def send_morning_agenda(phone: str, schedules: list[str]) -> None:
    """Send a morning message listing all active goals for the day.

    *schedules* is a list of schedule title strings.
    """
    items = "\n".join(f"  {i + 1}. {title}" for i, title in enumerate(schedules))
    body = (
        "☀️ *Good morning! Here's your Pursuit agenda for today:*\n\n"
        f"{items}\n\n"
        "Stay focused — you'll get your check-in reminder this evening. You've got this! 💪"
    )
    await send_text_message(phone, body)
    logger.info("whatsapp.morning_agenda_sent", to=phone, count=len(schedules))


async def send_interactive_checkin(
    phone: str,
    schedule_id: str,
    schedule_title: str,
    cl_balance: float,
) -> None:
    """Send the daily check-in interactive button card for a single schedule.

    Button IDs encode the schedule_id so the webhook knows which schedule
    was tapped: ``log_100:<schedule_id>``, ``log_50:<schedule_id>``,
    ``apply_cl:<schedule_id>``.

    Meta button IDs are limited to 256 chars and titles to 20 chars.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "header": {
                "type": "text",
                "text": "📅 Pursuit Evening Check-In",
            },
            "body": {
                "text": (
                    f'How much progress today on *"{schedule_title}"*?\n\n'
                    f"Skip Days left: *{cl_balance:.1f}* 🛋️"
                ),
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": f"log_100:{schedule_id}",
                            "title": "Done (100%) ✅",
                        },
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": f"log_50:{schedule_id}",
                            "title": "Halfway (50%) 🔄",
                        },
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": f"apply_cl:{schedule_id}",
                            "title": "Skip Day 🛋️",
                        },
                    },
                ],
            },
        },
    }
    url = f"{settings.meta_api_base_url}/{settings.meta_phone_number_id}/messages"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload, headers=_headers())
        resp.raise_for_status()
    logger.info("whatsapp.checkin_sent", to=phone, schedule=schedule_title)

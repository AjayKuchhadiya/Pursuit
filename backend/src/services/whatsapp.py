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
    """Send the OTP code as a plain-text message."""
    body = (
        f"🔐 Your Pursuit verification code is: *{otp}*\n\n"
        "This code expires in 5 minutes. Do not share it with anyone."
    )
    await send_text_message(phone, body)


async def send_interactive_checkin(
    phone: str,
    schedule_title: str,
    cl_balance: float,
) -> None:
    """Send the daily check-in interactive button card to *phone*.

    Produces a card with three tap buttons:
    - Done (100%)
    - Halfway (50%)
    - Apply Casual Leave
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "header": {
                "type": "text",
                "text": "📅 Pursuit Daily Check-In",
            },
            "body": {
                "text": (
                    f'Hey! How much progress did you make today on *"{schedule_title}"*?\n\n'
                    f"Casual Leaves remaining: *{cl_balance:.1f} CLs* 🛋️"
                ),
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": BUTTON_ID_DONE, "title": "Done (100%) ✅"},
                    },
                    {
                        "type": "reply",
                        "reply": {"id": BUTTON_ID_HALFWAY, "title": "Halfway (50%) 🔄"},
                    },
                    {
                        "type": "reply",
                        "reply": {"id": BUTTON_ID_CASUAL_LEAVE, "title": "Casual Leave 🛋️"},
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

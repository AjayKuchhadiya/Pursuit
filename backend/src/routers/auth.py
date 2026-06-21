"""Auth router – WhatsApp OTP → JWT."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, HTTPException, status

from core.exceptions import AppError
from core.security import create_access_token
from database import SupabaseDep
from schemas.auth import OtpRequestBody, OtpVerifyBody, TokenResponse
from services import otp as otp_svc
from services import whatsapp

OTP_TTL_MINUTES = 5

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger(__name__)


@router.post("/otp/request", status_code=status.HTTP_202_ACCEPTED)
async def request_otp(body: OtpRequestBody, db: SupabaseDep) -> dict:  # type: ignore[type-arg]
    """Generate an OTP, store its hash, and send it via WhatsApp."""
    code = otp_svc.generate_otp()
    hashed = otp_svc.hash_otp(code)
    expires_at = datetime.now(UTC) + timedelta(minutes=OTP_TTL_MINUTES)

    await db.table("otp_sessions").insert(
        {
            "phone_number": body.phone_number,
            "otp_hash": hashed,
            "expires_at": expires_at.isoformat(),
            "is_used": False,
        }
    ).execute()

    try:
        await whatsapp.send_otp_message(body.phone_number, code)
    except Exception as exc:
        logger.error("auth.otp_send_failed", phone=body.phone_number, error=str(exc))
        raise AppError(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send OTP via WhatsApp. Please try again.",
        ) from exc

    logger.info("auth.otp_requested", phone=body.phone_number)
    return {"detail": "OTP sent to your WhatsApp number."}


@router.post("/otp/verify", response_model=TokenResponse)
async def verify_otp(body: OtpVerifyBody, db: SupabaseDep) -> TokenResponse:
    """Verify the OTP, upsert the user, and return a JWT."""
    now = datetime.now(UTC).isoformat()

    result = (
        await db.table("otp_sessions")
        .select("*")
        .eq("phone_number", body.phone_number)
        .eq("is_used", False)
        .gt("expires_at", now)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid OTP found. Please request a new one.",
        )

    session = rows[0]
    if not otp_svc.verify_otp(body.otp, session["otp_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect OTP.",
        )

    # Mark OTP as used
    await db.table("otp_sessions").update({"is_used": True}).eq("id", session["id"]).execute()

    # Upsert user
    user_result = (
        await db.table("users")
        .upsert(
            {
                "phone_number": body.phone_number,
                "personality": "analyst",
                "timezone": "Asia/Kolkata",
                "is_active": True,
            },
            on_conflict="phone_number",
        )
        .select("id")
        .execute()
    )
    user_id: str = user_result.data[0]["id"]

    # Ensure leave_balance row exists
    await db.table("leave_balance").upsert(
        {"user_id": user_id, "balance": 3.0},
        on_conflict="user_id",
        ignore_duplicates=True,
    ).execute()

    token = create_access_token(user_id)
    logger.info("auth.otp_verified", user_id=user_id)
    return TokenResponse(access_token=token)

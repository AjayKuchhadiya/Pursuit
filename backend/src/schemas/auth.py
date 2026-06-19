"""Auth request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class OtpRequestBody(BaseModel):
    phone_number: str   # E.164 format, e.g. "+919876543210"


class OtpVerifyBody(BaseModel):
    phone_number: str
    otp: str            # 6-digit code the user received on WhatsApp


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

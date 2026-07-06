"""Auth request/response schemas."""

from __future__ import annotations

import re

from pydantic import BaseModel, field_validator

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


class OtpRequestBody(BaseModel):
    phone_number: str   # E.164 format, e.g. "+917457777777"

    @field_validator("phone_number")
    @classmethod
    def _must_be_e164(cls, v: str) -> str:
        if not _E164_RE.match(v):
            raise ValueError(
                "Phone number must be in E.164 format: "
                "a '+' followed by the country code and number, e.g. +917457878864"
            )
        return v


class OtpVerifyBody(BaseModel):
    phone_number: str
    otp: str            # 6-digit code the user received on WhatsApp

    @field_validator("phone_number")
    @classmethod
    def _must_be_e164(cls, v: str) -> str:
        if not _E164_RE.match(v):
            raise ValueError(
                "Phone number must be in E.164 format, e.g. +917457878864"
            )
        return v

    @field_validator("otp")
    @classmethod
    def _must_be_digits(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("OTP must be exactly 6 digits")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    is_new_user: bool = False

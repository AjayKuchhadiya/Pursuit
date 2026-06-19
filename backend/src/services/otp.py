"""OTP generation, hashing, and verification helpers."""

from __future__ import annotations

import secrets

from passlib.context import CryptContext

_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

OTP_LENGTH = 6


def generate_otp() -> str:
    """Return a cryptographically random ``OTP_LENGTH``-digit string."""
    return "".join([str(secrets.randbelow(10)) for _ in range(OTP_LENGTH)])


def hash_otp(otp: str) -> str:
    """Return a bcrypt hash of *otp*."""
    return _ctx.hash(otp)


def verify_otp(plain: str, hashed: str) -> bool:
    """Return ``True`` if *plain* matches *hashed*."""
    return _ctx.verify(plain, hashed)

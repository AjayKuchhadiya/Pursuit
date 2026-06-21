"""OTP generation, hashing, and verification helpers.

OTPs are short-lived (5 min) single-use 6-digit codes.
SHA-256 + hmac.compare_digest is perfectly secure for this use case
and avoids the passlib/bcrypt 4.x version incompatibility.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

OTP_LENGTH = 6


def generate_otp() -> str:
    """Return a cryptographically random ``OTP_LENGTH``-digit string."""
    return "".join([str(secrets.randbelow(10)) for _ in range(OTP_LENGTH)])


def hash_otp(otp: str) -> str:
    """Return a SHA-256 hex digest of *otp*."""
    return hashlib.sha256(otp.encode()).hexdigest()


def verify_otp(plain: str, hashed: str) -> bool:
    """Return ``True`` if *plain* matches *hashed* (timing-safe)."""
    return hmac.compare_digest(hashlib.sha256(plain.encode()).hexdigest(), hashed)

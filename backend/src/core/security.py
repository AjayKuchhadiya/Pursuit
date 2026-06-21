"""JWT creation and verification helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from config import settings


def create_access_token(subject: str) -> str:
    """Create a signed JWT whose *sub* claim is *subject* (the user's UUID)."""
    expire = datetime.now(UTC) + timedelta(days=settings.jwt_access_token_expire_days)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> str:
    """Decode a JWT and return the *sub* claim (user UUID).

    Raises :class:`jose.JWTError` on any validation failure.
    """
    data = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    sub: str | None = data.get("sub")
    if sub is None:
        raise JWTError("Token has no 'sub' claim")
    return sub

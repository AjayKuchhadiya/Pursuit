"""FastAPI dependencies shared across routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from core.security import decode_token
from database import SupabaseDep

_bearer = HTTPBearer()


async def get_current_user(
    db: SupabaseDep,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:  # type: ignore[type-arg]
    """Validate the Bearer JWT and return the matching user row from Supabase."""
    try:
        user_id = decode_token(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    result = await db.table("users").select("*").eq("id", user_id).maybe_single().execute()
    if result.data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return result.data  # type: ignore[return-value]


CurrentUser = Annotated[dict, Depends(get_current_user)]  # type: ignore[type-arg]

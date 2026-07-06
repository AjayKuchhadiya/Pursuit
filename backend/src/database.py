"""Supabase async client singleton and FastAPI dependency."""

from __future__ import annotations

from typing import Annotated, TypeAlias

from fastapi import Depends
from supabase._async.client import AsyncClient, create_client

from config import settings

_client: AsyncClient | None = None


async def get_supabase() -> AsyncClient:
    """Return (or lazily initialise) the shared async Supabase client.

    Uses the **service-role key** so server-side code can bypass Row Level
    Security.  Never expose this client to untrusted callers.
    """
    global _client
    if _client is None:
        _client = await create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return _client


# Convenience type alias for route dependencies
SupabaseDep: TypeAlias = Annotated[AsyncClient, Depends(get_supabase)]

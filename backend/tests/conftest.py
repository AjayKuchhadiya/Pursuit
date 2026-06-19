"""Shared pytest fixtures."""

from __future__ import annotations

from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import create_app


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
async def client(app) -> AsyncIterator[AsyncClient]:
    """Async test client with a mocked Supabase dependency."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture()
def mock_db():
    """Return a mock Supabase AsyncClient whose table() calls can be configured."""
    db = MagicMock()
    # Default chain: db.table("x").select("*").eq(...).execute() → data=[]
    chain = MagicMock()
    chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    chain.select = MagicMock(return_value=chain)
    chain.insert = MagicMock(return_value=chain)
    chain.update = MagicMock(return_value=chain)
    chain.upsert = MagicMock(return_value=chain)
    chain.eq = MagicMock(return_value=chain)
    chain.gt = MagicMock(return_value=chain)
    chain.gte = MagicMock(return_value=chain)
    chain.lte = MagicMock(return_value=chain)
    chain.limit = MagicMock(return_value=chain)
    chain.order = MagicMock(return_value=chain)
    chain.maybe_single = MagicMock(return_value=chain)
    db.table = MagicMock(return_value=chain)
    return db

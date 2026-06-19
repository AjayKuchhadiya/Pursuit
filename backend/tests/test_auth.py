"""Tests for auth routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_request_otp_returns_202(client, mock_db):
    with (
        patch("pursuit_api.routers.auth.get_supabase", return_value=mock_db),
        patch("pursuit_api.routers.auth.whatsapp.send_otp_message", new_callable=AsyncMock),
    ):
        resp = await client.post("/auth/otp/request", json={"phone_number": "+919876543210"})
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_verify_otp_invalid_returns_400(client, mock_db):
    """No matching OTP session → 400."""
    mock_db.table().execute = AsyncMock(return_value=type("R", (), {"data": []})())
    with patch("pursuit_api.routers.auth.get_supabase", return_value=mock_db):
        resp = await client.post(
            "/auth/otp/verify", json={"phone_number": "+919876543210", "otp": "000000"}
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_verify_otp_wrong_code_returns_400(client, mock_db):
    """Existing session but wrong OTP → 400."""
    from services.otp import hash_otp

    future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    session = {"id": "abc", "otp_hash": hash_otp("123456"), "expires_at": future}

    execute_mock = AsyncMock(return_value=type("R", (), {"data": [session]})())
    mock_db.table().execute = execute_mock
    mock_db.table().eq().execute = execute_mock

    with patch("pursuit_api.routers.auth.get_supabase", return_value=mock_db):
        resp = await client.post(
            "/auth/otp/verify", json={"phone_number": "+919876543210", "otp": "999999"}
        )
    assert resp.status_code == 400

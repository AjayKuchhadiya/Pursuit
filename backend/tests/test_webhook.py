"""Tests for Meta webhook routes."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_webhook_verification(client):
    """GET /webhook with correct verify_token echoes hub.challenge."""
    from config import settings

    resp = await client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.meta_webhook_verify_token,
            "hub.challenge": "test_challenge_xyz",
        },
    )
    assert resp.status_code == 200
    assert resp.text == '"test_challenge_xyz"'


@pytest.mark.asyncio
async def test_webhook_verification_wrong_token(client):
    """GET /webhook with wrong token → 403."""
    resp = await client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "xyz",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_status_update_ignored(client, mock_db):
    """Non-message webhook payloads (status updates) return status=ignored."""
    from unittest.mock import patch

    payload = {"entry": [{"changes": [{"value": {"statuses": [{}]}}]}]}
    with patch("pursuit_api.routers.webhook.get_supabase", return_value=mock_db):
        resp = await client.post("/webhook", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"

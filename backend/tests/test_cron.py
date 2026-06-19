"""Tests for the cron endpoint."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_cron_ping_wrong_secret_returns_403(client):
    resp = await client.post("/cron/daily-ping", headers={"X-Cron-Secret": "wrong-secret"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cron_ping_missing_header_returns_422(client):
    resp = await client.post("/cron/daily-ping")
    assert resp.status_code == 422

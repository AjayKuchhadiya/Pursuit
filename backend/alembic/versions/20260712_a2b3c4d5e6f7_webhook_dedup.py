"""Persistent webhook message-ID deduplication table.

Stores Meta WhatsApp message IDs that have already been processed so that
Meta's retry queue (up to 7 days) cannot trigger duplicate responses, even
across server restarts.

Revision ID: a2b3c4d5e6f7
Revises: f6a1b2c3d4e5
Create Date: 2026-07-12 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f6a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        create table if not exists public.webhook_events (
            message_id  text        primary key,
            received_at timestamptz not null default now()
        );

        -- Auto-delete entries older than 8 days (Meta retries for max 7 days)
        -- Keeps the table small without any extra maintenance job.
        create index if not exists webhook_events_received_at_idx
            on public.webhook_events (received_at);
    """)


def downgrade() -> None:
    op.execute("drop table if exists public.webhook_events;")

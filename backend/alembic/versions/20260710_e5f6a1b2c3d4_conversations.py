"""Add conversations table for WhatsApp chat history.

Stores the last N messages per user so the conversational agent
has short-term memory across exchanges.

Revision ID: e5f6a1b2c3d4
Revises: d4e5f6a1b2c3
Create Date: 2026-07-10 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "e5f6a1b2c3d4"
down_revision: Union[str, None] = "d4e5f6a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        create table if not exists public.conversations (
            id         uuid primary key default gen_random_uuid(),
            user_id    uuid not null references public.users(id) on delete cascade,
            role       text not null check (role in ('user', 'model')),
            content    text not null,
            created_at timestamptz not null default now()
        )
    """)
    op.execute(
        "create index if not exists conversations_user_id_created_at_idx "
        "on public.conversations(user_id, created_at desc)"
    )


def downgrade() -> None:
    op.execute("drop index if exists conversations_user_id_created_at_idx")
    op.execute("drop table if exists public.conversations")

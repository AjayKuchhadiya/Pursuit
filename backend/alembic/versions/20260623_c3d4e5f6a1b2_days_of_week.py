"""Add days_of_week to schedules.

Revision ID: c3d4e5f6a1b2
Revises: b2c3d4e5f6a1
Create Date: 2026-06-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c3d4e5f6a1b2"
down_revision = "b2c3d4e5f6a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add days_of_week as integer array; default all 7 days (0=Mon … 6=Sun)
    op.add_column(
        "schedules",
        sa.Column(
            "days_of_week",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default="{0,1,2,3,4,5,6}",
        ),
    )


def downgrade() -> None:
    op.drop_column("schedules", "days_of_week")

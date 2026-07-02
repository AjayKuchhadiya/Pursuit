"""Application factory and entry point."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import structlog
import uvicorn
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError

from config import settings
from core.exceptions import (
    AppError,
    app_error_handler,
    generic_error_handler,
    jwt_error_handler,
)
from database import get_supabase
from routers import auth, cron, leaves, logs, rewards, schedules, users, webhook

logger = structlog.get_logger(__name__)

# Resolve alembic.ini relative to this file so it works regardless of cwd
_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


def _run_migrations() -> None:
    """Run any pending Alembic migrations synchronously.

    Called once during application startup before the server starts
    accepting requests.  Safe to run on every start — Alembic is a no-op
    when the database is already at ``head``.
    """
    cfg = AlembicConfig(str(_ALEMBIC_INI))
    # Ensure the versions directory is resolved relative to alembic.ini, not cwd
    cfg.set_main_option("script_location", str(_ALEMBIC_INI.parent / "alembic"))
    alembic_command.upgrade(cfg, "head")
    logger.info("startup.migrations_applied")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run migrations then verify Supabase connectivity on startup."""
    # ── 1. Auto-migrate ───────────────────────────────────────────────────────
    # Skipped in production: Supabase's pooler requires a direct TCP connection
    # that isn't reliably available on all hosting platforms. Apply migrations
    # manually via `alembic upgrade head` locally or via Supabase Dashboard →
    # SQL Editor when deploying schema changes to production.
    if settings.app_env != "production":
        try:
            _run_migrations()
        except Exception as exc:  # noqa: BLE001
            logger.error("startup.migrations_failed", error=str(exc))
            # Don't crash the server — log and continue so the app stays debuggable
    else:
        logger.info("startup.migrations_skipped", reason="production environment")

    # ── 2. Supabase health-check ──────────────────────────────────────────────
    try:
        db = await get_supabase()
        await db.table("users").select("id").limit(1).execute()
        logger.info("startup.supabase_connected")
    except Exception as exc:  # noqa: BLE001
        logger.error("startup.supabase_failed", error=str(exc))

    yield
    logger.info("shutdown.complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Pursuit API",
        description="Gamified WhatsApp accountability partner – backend",
        version="0.1.0",
        lifespan=lifespan,
        # In production, hide docs behind auth or disable entirely
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ────────────────────────────────────────────────────
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(JWTError, jwt_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_error_handler)  # type: ignore[arg-type]

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(auth.router)
    app.include_router(webhook.router)
    app.include_router(schedules.router)
    app.include_router(logs.router)
    app.include_router(leaves.router)
    app.include_router(rewards.router)
    app.include_router(users.router)
    app.include_router(cron.router)

    @app.get("/health", tags=["health"])
    async def health() -> dict:  # type: ignore[type-arg]
        return {"status": "ok"}

    return app


app = create_app()


def run() -> None:
    """Entry point for ``uv run serve``."""
    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # noqa: S104
        port=8000,
        reload=settings.app_env == "development",
    )

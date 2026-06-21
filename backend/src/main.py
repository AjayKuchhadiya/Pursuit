"""Application factory and entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
import uvicorn
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


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Verify Supabase connectivity on startup."""
    try:
        db = await get_supabase()
        # Lightweight health-check: list tables in public schema
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

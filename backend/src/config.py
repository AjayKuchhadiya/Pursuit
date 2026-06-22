"""Application settings loaded from environment / .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Always resolve .env relative to this file's parent (backend/), regardless
# of which directory the server is launched from.
_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # ── Database (Alembic) ────────────────────────────────────────────────────
    database_url: str

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_days: int = 7

    # ── Meta WhatsApp Cloud API ───────────────────────────────────────────────
    meta_access_token: str
    meta_phone_number_id: str
    meta_whatsapp_api_version: str = "v19.0"
    meta_webhook_verify_token: str

    # ── Cron ──────────────────────────────────────────────────────────────────
    cron_secret: str

    # ── App ───────────────────────────────────────────────────────────────────
    app_env: str = "development"
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def meta_api_base_url(self) -> str:
        return f"https://graph.facebook.com/{self.meta_whatsapp_api_version}"


# Single shared instance – import this everywhere.
settings = Settings()  # type: ignore[call-arg]

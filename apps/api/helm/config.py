"""Application settings sourced from environment variables.

Load order: process env → .env.local → .env. Pydantic validates types at access.
All fields are optional so the app can import (and /health can respond) even in
a bare CI environment; code paths that require a value must check for its presence.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> tuple[str, ...]:
    """Absolute paths to the root .env + .env.local, best-effort.

    In a local checkout the module is at `apps/api/helm/config.py`, so
    `parents[3]` resolves to the repo root and we pick up `.env.local`
    regardless of the CWD the process was launched from (uvicorn from
    `apps/api`, alembic from `apps/api`, scripts from anywhere).

    In the Docker image `WORKDIR=/app` and the module is at `/app/helm/config.py`
    — only 2 parents exist. We return `()` in that case; Render, Fly, and
    other container hosts inject env vars directly into the process env,
    which pydantic-settings reads without needing a file.
    """
    try:
        root = Path(__file__).resolve().parents[3]
    except IndexError:
        return ()
    return tuple(str(root / name) for name in (".env", ".env.local"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: str = Field("development", alias="ENV")
    log_level: str = Field("info", alias="LOG_LEVEL")
    api_base_url: str = Field("http://localhost:8000", alias="API_BASE_URL")
    web_base_url: str = Field("http://localhost:3000", alias="WEB_BASE_URL")

    # CORS — comma-separated list of origins allowed to call the API.
    # Local dev defaults to the Next dev server; prod sets the Vercel domain
    # in Render env. Empty string = CORS disabled (API unreachable from browser).
    web_origin_allowlist: str = Field(default="http://localhost:3000", alias="WEB_ORIGIN_ALLOWLIST")

    # Database — Supabase Postgres
    database_url: str = Field("", alias="DATABASE_URL")

    # Supabase auth
    supabase_url: str = Field("", alias="SUPABASE_URL")
    supabase_anon_key: str = Field("", alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field("", alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret: str = Field("", alias="SUPABASE_JWT_SECRET")

    redis_url: str = Field("redis://localhost:6379", alias="REDIS_URL")

    # Observability
    sentry_dsn: str = Field("", alias="SENTRY_DSN")
    langfuse_public_key: str = Field("", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field("", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field("https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    # Expo push (optional). Used to authorize server-to-Expo push sends via
    # the Enhanced Security bearer. When unset, Expo accepts unauthenticated
    # sends in dev.
    expo_access_token: str = Field("", alias="EXPO_ACCESS_TOKEN")

    # Phase 1+ — not yet exercised
    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")
    composio_api_key: str = Field("", alias="COMPOSIO_API_KEY")
    composio_mcp_url: str = Field("https://mcp.composio.dev", alias="COMPOSIO_MCP_URL")
    composio_webhook_secret: str = Field("", alias="COMPOSIO_WEBHOOK_SECRET")

    # Phase 2+
    stripe_secret_key: str = Field("", alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field("", alias="STRIPE_WEBHOOK_SECRET")
    stripe_issuing_enabled: bool = Field(default=False, alias="STRIPE_ISSUING_ENABLED")

    # Defaults
    default_weekly_spend_cap_cents: int = Field(
        default=50000, alias="DEFAULT_WEEKLY_SPEND_CAP_CENTS"
    )
    default_per_auth_cap_cents: int = Field(default=50000, alias="DEFAULT_PER_AUTH_CAP_CENTS")
    default_approval_threshold_cents: int = Field(
        default=10000, alias="DEFAULT_APPROVAL_THRESHOLD_CENTS"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

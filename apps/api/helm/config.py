"""Application settings sourced from environment variables.

Load order: process env → .env.local → .env. Pydantic validates types at access.
All fields are optional so the app can import (and /health can respond) even in
a bare CI environment; code paths that require a value must check for its presence.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: str = Field("development", alias="ENV")
    log_level: str = Field("info", alias="LOG_LEVEL")
    api_base_url: str = Field("http://localhost:8000", alias="API_BASE_URL")
    web_base_url: str = Field("http://localhost:3000", alias="WEB_BASE_URL")

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

    # Phase 1+ — not yet exercised
    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")
    composio_api_key: str = Field("", alias="COMPOSIO_API_KEY")
    composio_mcp_url: str = Field("https://mcp.composio.dev", alias="COMPOSIO_MCP_URL")

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

"""Liveness + readiness probes.

GET /health is the liveness check — process responds, that's it. No DB
touch, so alerts can distinguish app-down from DB-down.

GET /ready is the readiness check used by load balancers / Render's
health check / k8s readiness gates. Probes the DB with a SELECT 1 and
reports which integrations are configured (no outbound calls — those
add latency that would back up the LB). Returns 503 when DB is
unreachable so traffic is shed gracefully.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from helm import __version__
from helm.config import get_settings
from helm.db.session import session_scope

router = APIRouter(tags=["meta"])
log = structlog.get_logger("helm.health")


@router.get("/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "helm-api",
        "version": __version__,
        "env": settings.env,
    }


@router.get("/ready")
async def ready() -> dict[str, Any]:
    settings = get_settings()
    integrations = {
        "anthropic": bool(settings.anthropic_api_key),
        "composio": bool(settings.composio_api_key),
        "stripe": bool(settings.stripe_secret_key),
        "stripe_issuing": settings.stripe_issuing_enabled,
        "supabase": bool(settings.supabase_url and settings.supabase_anon_key),
        "openai": bool(settings.openai_api_key),
        "sentry": bool(settings.sentry_dsn),
        "langfuse": bool(settings.langfuse_public_key and settings.langfuse_secret_key),
    }

    db_ok = True
    db_error: str | None = None
    try:
        async with session_scope() as db:
            await db.execute(text("SELECT 1"))
    except SQLAlchemyError as e:
        db_ok = False
        db_error = str(e)[:200]
        log.warning("ready.db_probe_failed", err=db_error)

    body: dict[str, Any] = {
        "status": "ok" if db_ok else "degraded",
        "service": "helm-api",
        "version": __version__,
        "env": settings.env,
        "db": "ok" if db_ok else "error",
        "integrations": integrations,
    }
    if db_error:
        body["db_error"] = db_error

    if not db_ok:
        # 503 so a load balancer pulls us out of the pool until the DB
        # recovers. Process stays up — /health still returns 200.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=body)
    return body

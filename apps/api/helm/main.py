"""FastAPI app factory.

Exposes `app` for uvicorn. Lifespan wires logging + Sentry on startup and flushes
on shutdown. Routes are included inside `create_app()` so tests can build fresh apps.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI

from helm.config import get_settings
from helm.logging import configure_logging
from helm.middleware import CorrelationIdMiddleware
from helm.routes import approvals as approvals_routes
from helm.routes import auth as auth_routes
from helm.routes import businesses as businesses_routes
from helm.routes import chat as chat_routes
from helm.routes import health as health_routes
from helm.routes import integrations as integrations_routes
from helm.routes import kill_switch as kill_switch_routes
from helm.routes import stripe as stripe_routes
from helm.routes import webhooks as webhooks_routes


def _init_sentry() -> None:
    settings = get_settings()
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        send_default_pii=False,
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    _init_sentry()
    log = structlog.get_logger("helm.api")
    settings = get_settings()
    log.info("api.startup", env=settings.env, version="0.0.0")
    try:
        yield
    finally:
        log.info("api.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Helm API",
        version="0.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.include_router(health_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(kill_switch_routes.router)
    app.include_router(businesses_routes.router)
    app.include_router(approvals_routes.router)
    app.include_router(integrations_routes.router)
    app.include_router(webhooks_routes.router)
    app.include_router(stripe_routes.router)
    return app


app = create_app()

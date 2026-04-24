"""FastAPI app factory.

Exposes `app` for uvicorn. Lifespan wires logging + Sentry on startup and flushes
on shutdown. Routes are included inside `create_app()` so tests can build fresh apps.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from helm.config import get_settings
from helm.logging import configure_logging
from helm.middleware import TRACE_HEADER, CorrelationIdMiddleware
from helm.routes import approvals as approvals_routes
from helm.routes import auth as auth_routes
from helm.routes import billing as billing_routes
from helm.routes import brand_library as brand_library_routes
from helm.routes import builder as builder_routes
from helm.routes import businesses as businesses_routes
from helm.routes import canvas as canvas_routes
from helm.routes import chat as chat_routes
from helm.routes import connections as connections_routes
from helm.routes import creatives as creatives_routes
from helm.routes import credits as credits_routes
from helm.routes import events as events_routes
from helm.routes import expenses as expenses_routes
from helm.routes import health as health_routes
from helm.routes import integrations as integrations_routes
from helm.routes import kill_switch as kill_switch_routes
from helm.routes import launches as launches_routes
from helm.routes import reformat as reformat_routes
from helm.routes import renders as renders_routes
from helm.routes import scheduled_posts as scheduled_posts_routes
from helm.routes import storefronts as storefronts_routes
from helm.routes import stripe as stripe_routes
from helm.routes import today as today_routes
from helm.routes import webhooks as webhooks_routes
from helm.services import launch_workflow, scheduler, tracing


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
    # Resume any launches that were mid-flight when the previous process
    # stopped. Best-effort — a DB outage here shouldn't block startup.
    try:
        resumed = await launch_workflow.resume_pending_launches()
        if resumed:
            log.info("api.launches_resumed", count=resumed)
    except Exception as e:
        log.warning("api.launches_resume_failed", err=str(e)[:200])
    # Start the in-process scheduler. No-op when HELM_SCHEDULER_ENABLED=false
    # (tests, local dev without Composio/Stripe).
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()
        tracing.flush()
        log.info("api.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Helm API",
        version="0.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    # CORS — parse the env allowlist into a list of origins.
    # Origins are compared exact-match (scheme + host + port). Use a
    # FastAPI-level allowlist rather than * because we pass Authorization
    # bearer tokens and want the browser to honor CORS credentials rules.
    settings = get_settings()
    origins = [o.strip() for o in settings.web_origin_allowlist.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["x-trace-id"],
            max_age=86400,
        )

    app.add_middleware(CorrelationIdMiddleware)

    log = structlog.get_logger("helm.api")

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", None) or ""
        detail = exc.detail
        if isinstance(detail, dict):
            body: dict[str, object] = {**detail}
            if trace_id and "trace_id" not in body:
                body["trace_id"] = trace_id
        else:
            body = {"message": str(detail), "trace_id": trace_id}
        headers = dict(exc.headers or {})
        if trace_id:
            headers.setdefault(TRACE_HEADER, trace_id)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": body},
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", None) or ""
        # Sentry's FastAPI integration auto-captures; log locally too so the
        # trace_id + path + exception type are greppable in stdout.
        log.error(
            "request.unhandled_exception",
            exc_type=type(exc).__name__,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "error": "internal_error",
                    "message": (
                        "Something went wrong on our side. If it keeps "
                        "happening, email support@helm.app with this reference."
                    ),
                    "trace_id": trace_id,
                }
            },
            headers={TRACE_HEADER: trace_id} if trace_id else {},
        )

    app.include_router(health_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(kill_switch_routes.router)
    app.include_router(businesses_routes.router)
    app.include_router(brand_library_routes.router)
    app.include_router(builder_routes.router)
    app.include_router(builder_routes.public_router)
    app.include_router(canvas_routes.router)
    app.include_router(launches_routes.router)
    app.include_router(reformat_routes.router)
    app.include_router(renders_routes.router)
    app.include_router(scheduled_posts_routes.router)
    app.include_router(approvals_routes.router)
    app.include_router(connections_routes.router)
    app.include_router(creatives_routes.router)
    app.include_router(credits_routes.router)
    app.include_router(events_routes.router)
    app.include_router(expenses_routes.router)
    app.include_router(integrations_routes.router)
    app.include_router(webhooks_routes.router)
    app.include_router(stripe_routes.router)
    app.include_router(today_routes.router)
    app.include_router(billing_routes.router)
    app.include_router(storefronts_routes.admin_router)
    app.include_router(storefronts_routes.public_router)
    return app


app = create_app()

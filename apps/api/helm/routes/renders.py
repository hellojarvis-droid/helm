"""Creative Studio renders — REST + SSE.

    POST /renders                 — kick off a render (sync up to provider's
                                    start call; terminal status may be set
                                    immediately for synchronous providers)
    GET  /renders                 — list the user's renders (newest first)
    GET  /renders/stream          — SSE feed of status transitions
    GET  /renders/{id}            — fetch a single render
    POST /renders/{id}/cancel     — best-effort cancel
    GET  /renders/estimate        — preview cost without submitting

All tenant-scoped: queries filter by `user_id = current user`, business
filter optional.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.models import RenderJob
from helm.db.session import get_session, session_scope
from helm.db.tenant import get_business_for_user
from helm.errors import ClientError
from helm.services import providers, render_worker
from helm.services.integration_vault import ProviderKeyMissingError
from helm.services.render_worker import InvalidRenderRequestError
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(tags=["renders"])
log = structlog.get_logger("helm.renders")


# ──────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────


class RenderResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    business_id: uuid.UUID | None
    provider: str
    mode: str
    prompt: str
    options: dict[str, Any]
    status: str
    external_job_id: str | None
    output_url: str | None
    thumbnail_url: str | None
    cost_cents_estimate: int
    cost_cents_actual: int | None
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: RenderJob) -> RenderResponse:
        return cls(
            id=row.id,
            user_id=row.user_id,
            business_id=row.business_id,
            provider=row.provider,
            mode=row.mode,
            prompt=row.prompt,
            options=row.options,
            status=row.status,
            external_job_id=row.external_job_id,
            output_url=row.output_url,
            thumbnail_url=row.thumbnail_url,
            cost_cents_estimate=row.cost_cents_estimate,
            cost_cents_actual=row.cost_cents_actual,
            error=row.error,
            started_at=row.started_at,
            completed_at=row.completed_at,
            created_at=row.created_at,
        )


class StartRenderRequest(BaseModel):
    provider: Annotated[str, Field(min_length=2, max_length=40)]
    mode: Annotated[str, Field(description="'image' | 'video'")]
    prompt: Annotated[str, Field(min_length=1, max_length=4000)]
    business_id: uuid.UUID | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class CostEstimateRequest(BaseModel):
    provider: str
    mode: str
    options: dict[str, Any] = Field(default_factory=dict)


class CostEstimateResponse(BaseModel):
    provider: str
    mode: str
    cost_cents_estimate: int
    supported: bool
    note: str = ""


# ──────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────


@router.post("/renders/estimate", response_model=CostEstimateResponse)
async def estimate(body: CostEstimateRequest) -> CostEstimateResponse:
    adapter = providers.lookup(body.provider)
    if adapter is None:
        return CostEstimateResponse(
            provider=body.provider,
            mode=body.mode,
            cost_cents_estimate=0,
            supported=False,
            note=f"unknown provider '{body.provider}'",
        )
    supported = (body.mode == "image" and adapter.supports_image) or (
        body.mode == "video" and adapter.supports_video
    )
    if not supported:
        return CostEstimateResponse(
            provider=body.provider,
            mode=body.mode,
            cost_cents_estimate=0,
            supported=False,
            note=f"{body.provider} does not support {body.mode} renders",
        )
    cents = adapter.estimate_cost_cents(mode=body.mode, options=body.options)
    return CostEstimateResponse(
        provider=body.provider,
        mode=body.mode,
        cost_cents_estimate=cents,
        supported=True,
    )


@router.post("/renders", response_model=RenderResponse, status_code=201)
async def start_render(
    body: StartRenderRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> RenderResponse:
    user_row = await sync_user_from_supabase(db, user)

    if body.business_id is not None:
        biz = await get_business_for_user(db, user_row.id, body.business_id)
        if biz is None:
            raise HTTPException(status_code=404, detail="business not found")

    try:
        job = await render_worker.start_render(
            db,
            user_id=user_row.id,
            business_id=body.business_id,
            provider_slug=body.provider,
            mode=body.mode,
            prompt=body.prompt,
            options=body.options,
        )
    except InvalidRenderRequestError as e:
        raise ClientError(
            "invalid_render_request",
            status_code=422,
            message=str(e),
        ) from e
    except ProviderKeyMissingError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "provider_not_connected",
                "provider": e.provider,
                "message": (
                    f"Connect your {e.provider} account on the Connections page "
                    "before running renders."
                ),
            },
        ) from e
    return RenderResponse.from_row(job)


@router.get("/renders", response_model=list[RenderResponse])
async def list_renders(
    business_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before_id: uuid.UUID | None = None,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[RenderResponse]:
    user_row = await sync_user_from_supabase(db, user)
    q = select(RenderJob).where(RenderJob.user_id == user_row.id)
    if business_id is not None:
        q = q.where(RenderJob.business_id == business_id)
    if before_id is not None:
        anchor = await db.get(RenderJob, before_id)
        if anchor is not None:
            q = q.where(RenderJob.created_at < anchor.created_at)
    q = q.order_by(RenderJob.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [RenderResponse.from_row(r) for r in rows]


# NOTE: Define the fixed-path endpoints BEFORE the `/{render_id}` wildcard.
# FastAPI matches routes in registration order, and `/renders/stream` would
# otherwise be parsed as render_id="stream" and fail UUID validation.


@router.get("/renders/stream")
async def stream_renders(
    business_id: uuid.UUID | None = None,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """SSE feed of render transitions for the Studio queue UI.

    We poll the user's renders on a 1s tick (cheap local DB query) and emit
    a snapshot for any row whose status or output_url changed since the
    last poll. The stream closes after 10 minutes so long-lived tabs don't
    hold connections forever.
    """
    user_row = await sync_user_from_supabase(db, user)
    user_id = user_row.id

    async def iter_events() -> AsyncIterator[str]:
        # Initial snapshot so the client hydrates without a separate list call.
        async with session_scope() as streaming_db:
            q = select(RenderJob).where(RenderJob.user_id == user_id)
            if business_id is not None:
                q = q.where(RenderJob.business_id == business_id)
            rows = (
                (await streaming_db.execute(q.order_by(RenderJob.created_at.desc()).limit(50)))
                .scalars()
                .all()
            )
            yield _sse(
                "snapshot",
                {"renders": [RenderResponse.from_row(r).model_dump(mode="json") for r in rows]},
            )

        # Fingerprint per row: status + output_url. Any mismatch emits.
        fingerprint: dict[uuid.UUID, tuple[str, str | None]] = {
            r.id: (r.status, r.output_url) for r in rows
        }
        for _tick in range(600):  # ~10 min
            await asyncio.sleep(1.0)
            async with session_scope() as streaming_db:
                q = select(RenderJob).where(RenderJob.user_id == user_id)
                if business_id is not None:
                    q = q.where(RenderJob.business_id == business_id)
                current = (
                    (await streaming_db.execute(q.order_by(RenderJob.created_at.desc()).limit(50)))
                    .scalars()
                    .all()
                )

            changed: list[RenderJob] = []
            for row in current:
                prev = fingerprint.get(row.id)
                now_fp = (row.status, row.output_url)
                if prev != now_fp:
                    changed.append(row)
                    fingerprint[row.id] = now_fp

            if changed:
                yield _sse(
                    "renders",
                    {
                        "renders": [
                            RenderResponse.from_row(r).model_dump(mode="json") for r in changed
                        ]
                    },
                )

        yield _sse("timeout", {})

    return StreamingResponse(
        iter_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps({**data, 'kind': event}, default=str)}\n\n"


@router.get("/renders/{render_id}", response_model=RenderResponse)
async def get_render(
    render_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> RenderResponse:
    user_row = await sync_user_from_supabase(db, user)
    row = await db.get(RenderJob, render_id)
    if row is None or row.user_id != user_row.id:
        raise HTTPException(status_code=404, detail="render not found")
    return RenderResponse.from_row(row)


@router.post("/renders/{render_id}/cancel", response_model=RenderResponse)
async def cancel_render(
    render_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> RenderResponse:
    """Best-effort cancel. We flip our row to 'cancelled' but don't currently
    call the provider's cancel endpoint — charges already-accrued on the
    provider's side are unaffected. A follow-up adapter method can stop the
    upstream job when needed."""
    user_row = await sync_user_from_supabase(db, user)
    row = await db.get(RenderJob, render_id)
    if row is None or row.user_id != user_row.id:
        raise HTTPException(status_code=404, detail="render not found")
    if row.status in ("completed", "failed", "cancelled"):
        return RenderResponse.from_row(row)
    row.status = "cancelled"
    row.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    return RenderResponse.from_row(row)

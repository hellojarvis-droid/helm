"""Render worker — owns the lifecycle of a RenderJob row.

One entry point per operation:

    start_render  — client hits POST /renders; this decrypts the user's
                    key, calls provider.start, writes external_job_id,
                    flips to 'queued' or 'running' based on what the
                    provider said. Emits a render_job_started event.

    poll_in_flight — a scheduler tick (every 20s). Picks up jobs in
                    'queued' or 'running' status across all users, polls
                    each one, flips terminal statuses to 'completed' or
                    'failed', writes output_url + actual cost. Emits
                    render_job_completed / render_job_failed.

The poller runs inside the in-process scheduler so we don't stand up a
separate worker. At low volume that's fine; at scale we peel it out.

Cost semantics: `cost_cents_estimate` is written up-front from the
provider's adapter. `cost_cents_actual` is populated from the provider's
response when available — many providers don't return a per-job cost,
so that field stays NULL and the UI shows the estimate.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.db.models import RenderJob
from helm.db.session import session_scope
from helm.services import event_log, providers
from helm.services.integration_vault import ProviderKeyMissingError

log = structlog.get_logger("helm.render_worker")


class InvalidRenderRequestError(ValueError):
    """Raised when the provider/mode combo is invalid or options are wrong."""


async def start_render(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    business_id: uuid.UUID | None,
    provider_slug: str,
    mode: str,
    prompt: str,
    options: dict[str, Any],
) -> RenderJob:
    """Kick off a render. Raises `ProviderKeyMissingError` (route handler
    converts to 503) or `InvalidRenderRequestError` (422) on bad input.
    Returns the fresh RenderJob row."""
    adapter = providers.lookup(provider_slug)
    if adapter is None:
        raise InvalidRenderRequestError(f"unknown provider '{provider_slug}'")
    if mode not in ("image", "video"):
        raise InvalidRenderRequestError("mode must be 'image' or 'video'")
    if mode == "image" and not adapter.supports_image:
        raise InvalidRenderRequestError(f"{provider_slug} does not support image renders")
    if mode == "video" and not adapter.supports_video:
        raise InvalidRenderRequestError(f"{provider_slug} does not support video renders")
    if not prompt.strip():
        raise InvalidRenderRequestError("prompt is required")

    estimate = adapter.estimate_cost_cents(mode=mode, options=options)
    job = RenderJob(
        user_id=user_id,
        business_id=business_id,
        provider=provider_slug,
        mode=mode,
        prompt=prompt.strip(),
        options=options,
        status="pending",
        cost_cents_estimate=estimate,
    )
    db.add(job)
    await db.flush()

    try:
        api_key = await providers.get_api_key_for(
            db, user_id=user_id, provider_slug=provider_slug
        )
    except ProviderKeyMissingError:
        job.status = "failed"
        job.error = f"no connected {provider_slug} key — add one in Connections"
        job.completed_at = datetime.now(UTC)
        await db.commit()
        raise

    try:
        result = await adapter.start(
            mode=mode, prompt=job.prompt, options=options, api_key=api_key
        )
    except Exception as exc:  # network, SDK failure
        log.exception("render.start_crashed", provider=provider_slug)
        job.status = "failed"
        job.error = str(exc)[:500]
        job.completed_at = datetime.now(UTC)
        await db.commit()
        return job

    job.external_job_id = result.external_job_id
    job.started_at = datetime.now(UTC)
    if result.status == "failed":
        job.status = "failed"
        job.error = result.error or "provider rejected the request"
        job.completed_at = datetime.now(UTC)
    elif result.status == "completed":
        # Some providers return a synchronous result on start (image gen).
        job.status = "completed"
        job.output_url = result.output_url
        job.thumbnail_url = result.thumbnail_url
        job.cost_cents_actual = result.cost_cents_actual
        job.completed_at = datetime.now(UTC)
    else:
        job.status = result.status  # queued | running
    await db.commit()
    await db.refresh(job)

    if business_id is not None:
        # The render lives against a CEO-session-adjacent event so the
        # Events view shows it alongside agent tool calls. We route
        # through event_log in a fresh session to avoid coupling the
        # render_jobs commit to the event commit.
        await _emit_render_event(
            business_id=business_id,
            event_type=f"render_job_{job.status}",
            payload={
                "render_job_id": str(job.id),
                "provider": provider_slug,
                "mode": mode,
                "status": job.status,
                "cost_cents_estimate": estimate,
                "prompt_preview": prompt[:140],
            },
        )
    return job


async def poll_in_flight() -> dict[str, int]:
    """Scheduler tick. Poll every 'queued' or 'running' job and advance it."""
    advanced = 0
    unchanged = 0
    async with session_scope() as db:
        q = select(RenderJob).where(RenderJob.status.in_(("queued", "running")))
        rows = list((await db.execute(q)).scalars().all())

    for row in rows:
        try:
            moved = await _poll_one(row.id)
            if moved:
                advanced += 1
            else:
                unchanged += 1
        except Exception:
            log.exception("render.poll_one_crashed", render_id=str(row.id))

    return {"advanced": advanced, "unchanged": unchanged, "inspected": len(rows)}


async def _poll_one(job_id: uuid.UUID) -> bool:
    """Poll a single job. Returns True iff status changed."""
    async with session_scope() as db:
        job = await db.get(RenderJob, job_id)
        if job is None:
            return False
        if job.status not in ("queued", "running"):
            return False
        if not job.external_job_id:
            # Nothing to poll (shouldn't happen for queued/running).
            return False

        adapter = providers.lookup(job.provider)
        if adapter is None:
            job.status = "failed"
            job.error = f"provider '{job.provider}' no longer registered"
            job.completed_at = datetime.now(UTC)
            await db.commit()
            return True

        try:
            api_key = await providers.get_api_key_for(
                db, user_id=job.user_id, provider_slug=job.provider
            )
        except ProviderKeyMissingError:
            job.status = "failed"
            job.error = f"no connected {job.provider} key"
            job.completed_at = datetime.now(UTC)
            await db.commit()
            return True

        try:
            result = await adapter.poll(
                external_job_id=job.external_job_id, api_key=api_key
            )
        except Exception as exc:
            log.exception("render.poll_crashed", render_id=str(job.id))
            job.error = str(exc)[:500]
            await db.commit()
            return False

        moved = result.status != job.status
        if result.status == "completed":
            job.status = "completed"
            job.output_url = result.output_url
            job.thumbnail_url = result.thumbnail_url
            if result.cost_cents_actual is not None:
                job.cost_cents_actual = result.cost_cents_actual
            job.completed_at = datetime.now(UTC)
        elif result.status == "failed":
            job.status = "failed"
            job.error = result.error
            job.completed_at = datetime.now(UTC)
        elif result.status in ("queued", "running"):
            job.status = result.status

        if moved and job.status in ("completed", "failed"):
            bid = job.business_id
            if bid is not None:
                await _emit_render_event(
                    business_id=bid,
                    event_type=f"render_job_{job.status}",
                    payload={
                        "render_job_id": str(job.id),
                        "provider": job.provider,
                        "mode": job.mode,
                        "status": job.status,
                        "output_url": job.output_url,
                        "error": job.error,
                    },
                )

        await db.commit()
        return moved


async def _emit_render_event(
    *, business_id: uuid.UUID, event_type: str, payload: dict[str, Any]
) -> None:
    """Attach a render event to the user's most-recent business-scoped agent
    session so it shows up in the Events log alongside the swarm's work.
    Best-effort — a missing session just skips the emit."""
    from helm.db.models import AgentSession

    async with session_scope() as db:
        sess_q = await db.execute(
            select(AgentSession)
            .where(AgentSession.business_id == business_id)
            .order_by(AgentSession.last_active_at.desc())
            .limit(1)
        )
        sess = sess_q.scalar_one_or_none()
        if sess is None:
            return
        await event_log.write(
            db,
            session_id=sess.id,
            business_id=business_id,
            event_type=event_type,
            agent_name="muse",
            payload=payload,
        )

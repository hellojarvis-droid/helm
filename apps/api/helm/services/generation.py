"""Canvas generation service — unified kickoff across Image / Video /
Edit / Enhance / Lipsync.

This replaces the DAG-driven `creative_dag.run_dag` for the Canvas
surface. Each user click creates one `Generation` row, which wraps
one or more `RenderJob`s.

Flow:

    1. Resolve model from registry, estimate cost.
    2. Reserve credits (credits.reserve) — fail fast on insufficient.
    3. Write Generation row with status='queued'.
    4. Dispatch to `render_worker.start_render` with the right
       provider + mode. The render job progresses async via the
       existing render_worker poll tick.
    5. On poll-side terminal status flip, `sync_from_render_job` copies
       output_url + cost back to the generation + commits/refunds.

Failure never charges: on exception in step 4, refund full hold.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.db.models import Generation, RenderJob
from helm.services import credits, model_registry, render_worker
from helm.services.integration_vault import ProviderKeyMissingError

log = structlog.get_logger("helm.generation")


class GenerationError(Exception):
    """Kickoff failed for a non-credit reason (bad params, provider down)."""


_TOOL_TO_RENDER_MODE: dict[str, str] = {
    "image": "image",
    "video": "video",
    "edit": "image",
    "enhance": "image",
    "lipsync": "video",
}


async def create(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    business_id: uuid.UUID | None,
    session_id: uuid.UUID,
    tool: str,
    model: str,
    prompt: str,
    params: dict[str, Any] | None = None,
    references: list[dict[str, Any]] | None = None,
    parent_generation_id: uuid.UUID | None = None,
) -> Generation:
    """Kick off one Canvas generation. Returns the Generation row —
    status will be queued/running and the render worker drives it to
    completed or failed."""
    entry = model_registry.get(tool, model)  # type: ignore[arg-type]
    if entry is None:
        raise GenerationError(f"unknown model '{model}' for tool '{tool}'")

    params = params or {}
    references = references or []
    estimate = model_registry.estimate_cost_credits(
        tool=tool,  # type: ignore[arg-type]
        model=model,
        params=params,
    )

    reservation_id, _ = await credits.reserve(
        db,
        user_id=user_id,
        estimate_cents=estimate,
        reference_type=f"generation_{tool}",
        description=f"{entry.name} — {tool}",
        meta={
            "tool": tool,
            "model": model,
            "business_id": str(business_id) if business_id else None,
        },
    )
    await db.commit()

    gen = Generation(
        user_id=user_id,
        business_id=business_id,
        session_id=session_id,
        parent_generation_id=parent_generation_id,
        tool=tool,
        model=model,
        prompt=prompt,
        params=params,
        references=references,
        status="queued",
        cost_cents_reserved=estimate,
        reservation_id=reservation_id,
    )
    db.add(gen)
    await db.flush()
    generation_id = gen.id

    render_mode = _TOOL_TO_RENDER_MODE.get(tool)
    if render_mode is None:
        await _finalize_failed(
            db,
            generation_id=generation_id,
            reservation_id=reservation_id,
            user_id=user_id,
            reason=f"unsupported tool '{tool}'",
        )
        raise GenerationError(f"unsupported tool '{tool}'")

    # Translate Canvas references into provider options the render
    # worker can forward. Keep this boring — a richer mapping layer
    # lives in each adapter.
    provider_options = dict(params)
    for ref in references:
        role = str(ref.get("role", "")).lower()
        url = ref.get("url")
        if not url:
            continue
        if role in ("character", "style", "describe"):
            provider_options.setdefault("reference_image_url", url)
        elif role in ("magic_fill", "background_replace"):
            provider_options.setdefault("mask_source_url", url)

    try:
        job = await render_worker.start_render(
            db,
            user_id=user_id,
            business_id=business_id,
            provider_slug=entry.provider,
            mode=render_mode,
            prompt=prompt,
            options=provider_options,
        )
    except ProviderKeyMissingError as e:
        await _finalize_failed(
            db,
            generation_id=generation_id,
            reservation_id=reservation_id,
            user_id=user_id,
            reason=f"no key for {entry.provider}",
        )
        raise GenerationError(f"provider key missing: {e}") from e
    except render_worker.InvalidRenderRequestError as e:
        await _finalize_failed(
            db,
            generation_id=generation_id,
            reservation_id=reservation_id,
            user_id=user_id,
            reason=str(e)[:300],
        )
        raise GenerationError(str(e)) from e
    except Exception as e:
        log.exception("generation.start_crashed", gen_id=str(generation_id))
        await _finalize_failed(
            db,
            generation_id=generation_id,
            reservation_id=reservation_id,
            user_id=user_id,
            reason=str(e)[:300],
        )
        raise GenerationError(str(e)) from e

    # Link the RenderJob + mirror whatever status it already has.
    refreshed = await db.get(Generation, generation_id)
    if refreshed is None:
        raise GenerationError("generation vanished after kickoff")
    refreshed.render_job_ids = [str(job.id)]
    _mirror_render_status(refreshed, job)
    await db.commit()
    await db.refresh(refreshed)
    if refreshed.status in ("completed", "failed"):
        await _settle(db, refreshed)
    return refreshed


async def sync_from_render_jobs(db: AsyncSession, generation_id: uuid.UUID) -> None:
    """Called by the generation scheduler tick. Mirrors each linked
    RenderJob's state onto the Generation and settles credits when
    terminal."""
    gen = await db.get(Generation, generation_id)
    if gen is None or gen.status in ("completed", "failed", "cancelled"):
        return
    if not gen.render_job_ids:
        return

    # For v1 there's one render job per generation. Mirror + settle.
    job_id_str = gen.render_job_ids[0]
    try:
        job_id = uuid.UUID(job_id_str)
    except ValueError:
        return
    job = await db.get(RenderJob, job_id)
    if job is None:
        return
    _mirror_render_status(gen, job)
    if gen.status in ("completed", "failed"):
        await _settle(db, gen)
    await db.commit()


def _mirror_render_status(gen: Generation, job: RenderJob) -> None:
    gen.status = _render_to_gen_status(job.status)
    if gen.status == "completed":
        gen.output_url = job.output_url
        gen.thumbnail_url = job.thumbnail_url or job.output_url
    elif gen.status == "failed":
        gen.error = job.error or "render failed"
    gen.updated_at = datetime.now(UTC)


def _render_to_gen_status(render_status: str) -> str:
    if render_status in ("queued", "running", "pending"):
        return "running" if render_status != "pending" else "queued"
    return render_status  # completed / failed / cancelled


async def _settle(db: AsyncSession, gen: Generation) -> None:
    """Commit the actual cost against the reservation (or refund on failure)."""
    if gen.reservation_id is None:
        return
    # Idempotent: reuse the reserved estimate as the actual cost when
    # the render worker doesn't report a per-job price. The excess is
    # automatically refunded by credits.commit on under-use.
    if gen.status == "failed":
        await credits.refund(
            db,
            user_id=gen.user_id,
            reservation_id=gen.reservation_id,
            reason=gen.error or "generation failed",
        )
        gen.cost_cents_actual = 0
        return
    if gen.status == "completed":
        actual = gen.cost_cents_reserved or 0
        # If the linked render_job reports its own actual cost, prefer it.
        if gen.render_job_ids:
            try:
                job_id = uuid.UUID(gen.render_job_ids[0])
            except ValueError:
                job_id = None
            if job_id is not None:
                job = await db.get(RenderJob, job_id)
                if job is not None and job.cost_cents_actual is not None:
                    actual = job.cost_cents_actual
        await credits.commit(
            db,
            user_id=gen.user_id,
            reservation_id=gen.reservation_id,
            actual_cents=actual,
            description=f"{gen.model} · {gen.tool}",
            meta={"generation_id": str(gen.id), "tool": gen.tool, "model": gen.model},
        )
        gen.cost_cents_actual = actual


async def _finalize_failed(
    db: AsyncSession,
    *,
    generation_id: uuid.UUID,
    reservation_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str,
) -> None:
    gen = await db.get(Generation, generation_id)
    if gen is not None:
        gen.status = "failed"
        gen.error = reason
    await credits.refund(
        db,
        user_id=user_id,
        reservation_id=reservation_id,
        reason=reason,
    )
    await db.commit()


async def tick() -> dict[str, int]:
    """Scheduler tick — advance any queued/running generations by
    mirroring their linked RenderJob status. Short-lived sessions per
    generation to avoid long-held txns."""
    from helm.db.session import session_scope

    advanced = 0
    async with session_scope() as db:
        q = await db.execute(
            select(Generation.id).where(
                Generation.status.in_(("queued", "running"))
            )
        )
        gen_ids = [row[0] for row in q.all()]
    for gid in gen_ids:
        try:
            async with session_scope() as db:
                before = await db.get(Generation, gid)
                if before is None:
                    continue
                prev_status = before.status
                await sync_from_render_jobs(db, gid)
                after = await db.get(Generation, gid)
                if after is not None and after.status != prev_status:
                    advanced += 1
        except Exception:
            log.exception("generation.tick_crash", gen_id=str(gid))
    return {"advanced": advanced, "inspected": len(gen_ids)}

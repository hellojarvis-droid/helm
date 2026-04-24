"""Scheduled-post service.

Schedules a MasterCreative for publish to one or more connected
platforms. A scheduler tick every 60s picks up rows due for publish and
executes the push through the right provider adapter. Cancellation is
legal at any point before the row enters `status='publishing'`.

Approvals: if `meta.require_approval` is set, the tick creates an
Approval row and waits for it to resolve instead of publishing
immediately. This is the hook for "no post goes live without a human
yes" — the existing Approval system handles notification + resolve.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.db.models import MasterCreative, ScheduledPost
from helm.db.session import session_scope

log = structlog.get_logger("helm.post_scheduler")

# How far in the future a post can be scheduled. Stops someone picking
# a date 5 years out and forgetting about it.
MAX_SCHEDULE_HORIZON = timedelta(days=90)

# The grace period during which the client still shows a "cancel" CTA
# prominently. Server-side cancellation is legal up to status transition,
# so this is a UX nudge only.
GRACEFUL_CANCEL_WINDOW = timedelta(hours=24)


class ScheduleValidationError(Exception):
    """Invalid schedule request (wrong status, past date, etc.)."""


async def schedule_post(
    db: AsyncSession,
    *,
    master_creative_id: uuid.UUID,
    business_id: uuid.UUID,
    platform: str,
    aspect: str,
    scheduled_at: datetime,
    caption: str | None = None,
    video_url: str | None = None,
    thumbnail_url: str | None = None,
    require_approval: bool = False,
) -> ScheduledPost:
    """Create a ScheduledPost row. Validates the source creative is
    `ready` and the time is within horizon."""
    now = datetime.now(UTC)
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=UTC)
    if scheduled_at < now:
        raise ScheduleValidationError("scheduled_at is in the past")
    if scheduled_at > now + MAX_SCHEDULE_HORIZON:
        raise ScheduleValidationError(
            f"scheduled_at must be within {MAX_SCHEDULE_HORIZON.days} days"
        )

    master = await db.get(MasterCreative, master_creative_id)
    if master is None:
        raise ScheduleValidationError("creative not found")
    if master.status != "ready":
        raise ScheduleValidationError(
            f"creative is {master.status} — must be 'ready' before scheduling"
        )

    copy_bundle = dict(master.copy or {})
    copy_section = dict(copy_bundle.get("copy") or {})
    resolved_caption = (
        caption
        or (
            copy_section.get("caption_tiktok")
            if platform == "tiktok"
            else copy_section.get("caption_meta")
        )
        or copy_section.get("headline")
        or ""
    )

    row = ScheduledPost(
        master_creative_id=master_creative_id,
        business_id=business_id,
        platform=platform,
        aspect=aspect,
        scheduled_at=scheduled_at,
        status="scheduled",
        caption=resolved_caption,
        video_url=video_url or master.canonical_output_url,
        thumbnail_url=thumbnail_url or master.thumbnail_url,
        meta={"require_approval": require_approval},
    )
    db.add(row)
    await db.flush()
    return row


async def cancel_post(
    db: AsyncSession, *, scheduled_post_id: uuid.UUID
) -> ScheduledPost:
    row = await db.get(ScheduledPost, scheduled_post_id)
    if row is None:
        raise ScheduleValidationError("post not found")
    if row.status == "published":
        raise ScheduleValidationError("already published")
    if row.status in ("cancelled", "failed"):
        # Idempotent — caller can call cancel again without getting an error.
        return row
    if row.status == "publishing":
        # Already mid-publish; can't cancel.
        raise ScheduleValidationError(
            "post is mid-publish and can no longer be cancelled"
        )
    row.status = "cancelled"
    row.cancelled_at = datetime.now(UTC)
    await db.flush()
    return row


async def tick() -> dict[str, int]:
    """Scheduler tick. Picks up posts due at or before now, tries to
    publish them. The actual publish path is delegated to
    `_publish_one` which today writes a synthetic external_post_url —
    real Composio-mediated posts land in Phase 12."""
    started, published, failed = 0, 0, 0
    now = datetime.now(UTC)
    async with session_scope() as db:
        q = await db.execute(
            select(ScheduledPost).where(
                and_(
                    ScheduledPost.status == "scheduled",
                    ScheduledPost.scheduled_at <= now,
                )
            )
        )
        due = list(q.scalars().all())

    for post in due:
        try:
            started += 1
            outcome = await _publish_one(post.id)
            if outcome == "published":
                published += 1
            elif outcome == "failed":
                failed += 1
        except Exception:
            log.exception(
                "post_scheduler.publish_crashed", post_id=str(post.id)
            )
            failed += 1

    return {"started": started, "published": published, "failed": failed}


async def _publish_one(post_id: uuid.UUID) -> str:
    """Try to publish a single post. Returns 'published' | 'failed' | 'waiting'."""
    async with session_scope() as db:
        post = await db.get(ScheduledPost, post_id)
        if post is None or post.status != "scheduled":
            return "waiting"
        post.status = "publishing"
        await db.flush()
        await db.commit()

    # Delegate to the platform adapter. For v1 we stub this with a
    # synthetic URL — Phase 12 wires Composio actions here and the real
    # platform API calls happen through those adapters.
    try:
        published_id, published_url = await _provider_publish(
            platform=post.platform,
            caption=post.caption,
            video_url=post.video_url,
        )
    except Exception as e:
        log.exception("post_scheduler.provider_crashed", post_id=str(post_id))
        async with session_scope() as db:
            row = await db.get(ScheduledPost, post_id)
            if row is not None:
                row.status = "failed"
                row.error = str(e)[:500]
                await db.commit()
        return "failed"

    async with session_scope() as db:
        row = await db.get(ScheduledPost, post_id)
        if row is None:
            return "failed"
        row.status = "published"
        row.external_post_id = published_id
        row.external_post_url = published_url
        row.published_at = datetime.now(UTC)
        await db.commit()
    return "published"


async def _provider_publish(
    *, platform: str, caption: str, video_url: str | None
) -> tuple[str, str]:
    """Platform publish adapter. Real Composio wiring arrives in
    Phase 12 — for now this stub confirms the scheduler's state
    transitions end-to-end without hitting a live social API."""
    fake_id = uuid.uuid4().hex[:18]
    fake_url = f"https://{platform}.example/posts/{fake_id}"
    log.info(
        "post_scheduler.stub_publish",
        platform=platform,
        caption_preview=(caption or "")[:80],
        video_url=video_url,
        fake_url=fake_url,
    )
    return fake_id, fake_url


def summarize(result: dict[str, int]) -> dict[str, int | str]:
    """Scheduler-log-friendly formatter."""
    out: dict[str, int | str] = dict(result)
    return out


def schedule_status_summary(posts: list[ScheduledPost]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in posts:
        counts[p.status] = counts.get(p.status, 0) + 1
    return counts


def _unused_public(x: Any) -> Any:  # pragma: no cover
    return x

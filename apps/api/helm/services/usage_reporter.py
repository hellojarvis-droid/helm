"""Stripe usage reporter — post agent compute as metered usage.

After every chat turn we sum the user's `message.agent` cost_cents
strictly later than `users.last_usage_reported_at`, post a single
usage_record to the user's metered SubscriptionItem, and bump the
watermark. No metered item or no new events → no-op.

Best-effort and fire-and-forget so a slow Stripe call never delays a
chat turn. Failures log and leave the watermark unchanged so the next
report covers the same window plus whatever's accumulated since.

We bill on cost_cents (LLM expense to us, in pennies) so customers
see "your agents cost N this period" rather than raw token counts —
the price they actually care about. Stripe expects integer quantity
+ a "unit" string we declare on the price (e.g., "cents").
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.config import get_settings
from helm.db.models import AgentEvent, Business, User
from helm.db.session import session_scope
from helm.services.stripe_client import _configured_stripe, _in_thread

log = structlog.get_logger("helm.usage_reporter")

# Hold task refs so the GC doesn't cancel in-flight fire-and-forget reports.
_pending: set[asyncio.Task[None]] = set()


def schedule_report(user_id: str) -> None:
    """Fire-and-forget wrapper for chat-turn callers. Never raises."""
    task = asyncio.create_task(_safe_report(user_id))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def _safe_report(user_id: str) -> None:
    try:
        async with session_scope() as db:
            await report_usage_for_user(db, user_id)
    except Exception as e:
        log.warning("usage_reporter.failed", user_id=user_id, err=str(e)[:200])


async def report_usage_for_user(db: AsyncSession, user_id: str) -> int:
    """Aggregate + post metered usage for one user. Returns the cents
    reported (0 when nothing to do, including when Stripe isn't configured).
    """
    settings = get_settings()
    if not settings.stripe_secret_key:
        return 0

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.stripe_metered_item_id:
        return 0

    cutoff = user.last_usage_reported_at  # may be None on the first report

    # Sum message.agent cost_cents on this user's businesses since the cutoff,
    # AND track the latest event created_at so we can advance the watermark
    # to exactly there.
    sum_q = (
        select(
            func.coalesce(func.sum(AgentEvent.cost_cents), 0),
            func.max(AgentEvent.created_at),
        )
        .select_from(AgentEvent)
        .join(Business, Business.id == AgentEvent.business_id)
        .where(
            Business.user_id == user.id,
            AgentEvent.event_type == "message.agent",
        )
    )
    if cutoff is not None:
        sum_q = sum_q.where(AgentEvent.created_at > cutoff)

    row = (await db.execute(sum_q)).one()
    cents = int(row[0] or 0)
    latest: datetime | None = row[1]
    if cents <= 0 or latest is None:
        return 0

    s = _configured_stripe()
    item_id = user.stripe_metered_item_id

    def _post() -> None:
        s.SubscriptionItem.create_usage_record(
            item_id,
            quantity=cents,
            timestamp="now",
            action="increment",
        )

    await _in_thread(_post)
    user.last_usage_reported_at = latest
    await db.commit()
    log.info(
        "usage_reporter.reported",
        user_id=str(user.id),
        cents=cents,
        item_id=item_id,
    )
    return cents


def extract_user_payload(_: dict[str, Any]) -> None:  # pragma: no cover — parity stub
    """Intentionally unused — kept to mirror stripe_billing.extract_* shape."""
    return None

"""Stripe sync adapters registered with the sync_bus.

One entity today — `stripe_card_caps` — mirrors
`businesses.{weekly_spend_cap_cents, per_auth_cap_cents,
allowed_mcc_codes}` with Stripe Issuing's card-level spending_controls.

Push: Helm mutation calls
    `sync_bus.push("stripe_card_caps", external_id=<card_id>, payload={
      weekly_spend_cap_cents, per_auth_cap_cents, allowed_mcc_codes
    })`
and we translate to `stripe.issuing.Card.modify`.

Pull: the `/webhooks/stripe` route receives `issuing_card.updated` and
invokes `sync_bus.pull("stripe_card_caps", external_id=<card_id>, ...)`.
We reverse the translation and update our row — UNLESS Helm pushed
more recently than the webhook timestamp, in which case the pull
handler is skipped with `last_status='conflict'` so the UI can flag it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.config import get_settings
from helm.db.models import Business
from helm.services import stripe_client
from helm.services.sync_bus import PullContext, PushContext, SyncEntity, register

log = structlog.get_logger("helm.sync_stripe")


STRIPE_CARD_CAPS_ENTITY = "stripe_card_caps"


async def _push_card_caps(db: AsyncSession, ctx: PushContext) -> dict[str, Any]:
    """Outbound: push the business's caps + MCC allowlist to Stripe.

    `ctx.external_id` is the Stripe Issuing card id. The push is a no-op
    when Issuing is disabled (STRIPE_ISSUING_ENABLED=false) — we mark
    the record successful in that mode because Helm's DB stayed
    consistent with itself; Stripe just isn't the source of truth yet.
    """
    settings = get_settings()
    payload = ctx.payload
    weekly = int(payload.get("weekly_spend_cap_cents", 0))
    per_auth = int(payload.get("per_auth_cap_cents", 0))
    allowed_mcc: list[str] | None = payload.get("allowed_mcc_codes")
    account_id = payload.get("stripe_account_id")

    if not settings.stripe_issuing_enabled:
        return {"skipped": "issuing_not_enabled"}
    if not account_id:
        return {"skipped": "no_stripe_account"}

    await stripe_client.update_issuing_caps(
        account_id=str(account_id),
        card_id=ctx.external_id,
        weekly_spend_cap_cents=weekly,
        per_auth_cap_cents=per_auth,
        allowed_mcc_codes=allowed_mcc,
    )
    return {
        "weekly_spend_cap_cents": weekly,
        "per_auth_cap_cents": per_auth,
        "allowed_mcc_codes": allowed_mcc,
        "stripe_account_id": account_id,
    }


async def _pull_card_caps(db: AsyncSession, ctx: PullContext) -> dict[str, Any]:
    """Inbound: an `issuing_card.updated` webhook landed. Reflect the
    remote spending_controls onto our business row. Callers of sync_bus
    have already gated on Helm-wins semantics, so by the time we're
    here, the external event is strictly newer than the last local push.
    """
    payload = ctx.payload
    controls = payload.get("spending_controls") or {}
    limits = controls.get("spending_limits") or []
    weekly: int | None = None
    per_auth: int | None = None
    for limit in limits:
        interval = limit.get("interval")
        amount = limit.get("amount")
        if interval == "weekly" and isinstance(amount, int):
            weekly = amount
        elif interval == "per_authorization" and isinstance(amount, int):
            per_auth = amount
    allowed = controls.get("allowed_categories")
    allowed_mcc = list(allowed) if isinstance(allowed, list) else None

    biz_q = await db.execute(
        select(Business).where(Business.stripe_card_id == ctx.external_id)
    )
    biz = biz_q.scalar_one_or_none()
    if biz is None:
        return {"skipped": "no_business_for_card", "external_id": ctx.external_id}

    changed: dict[str, Any] = {}
    if weekly is not None and biz.weekly_spend_cap_cents != weekly:
        changed["weekly_spend_cap_cents"] = {
            "before": biz.weekly_spend_cap_cents,
            "after": weekly,
        }
        biz.weekly_spend_cap_cents = weekly
    if per_auth is not None and biz.per_auth_cap_cents != per_auth:
        changed["per_auth_cap_cents"] = {
            "before": biz.per_auth_cap_cents,
            "after": per_auth,
        }
        biz.per_auth_cap_cents = per_auth
    if allowed_mcc is not None and biz.allowed_mcc_codes != allowed_mcc:
        changed["allowed_mcc_codes"] = {
            "before": biz.allowed_mcc_codes,
            "after": allowed_mcc,
        }
        biz.allowed_mcc_codes = allowed_mcc
    if not changed:
        return {"skipped": "no_change"}
    await db.flush()
    log.info(
        "sync_stripe.pull_applied",
        card_id=ctx.external_id,
        business_id=str(biz.id),
        fields=list(changed.keys()),
    )
    return {"changed": changed}


register(
    SyncEntity(
        entity_type=STRIPE_CARD_CAPS_ENTITY,
        push_fn=_push_card_caps,
        pull_fn=_pull_card_caps,
    )
)


def stripe_event_timestamp(event: dict[str, Any]) -> datetime:
    """Extract a best-effort timestamp from a Stripe webhook event.

    Stripe sends `created` at the top level as unix seconds. If missing,
    fall back to now() — better to apply than to drop a legit update.
    """
    created = event.get("created")
    if isinstance(created, int):
        return datetime.fromtimestamp(created, tz=UTC)
    return datetime.now(UTC)

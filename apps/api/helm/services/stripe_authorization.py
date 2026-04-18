"""Real-time Stripe Issuing authorization decisions.

When a card is swiped / charged, Stripe POSTs `issuing_authorization.request`
and waits up to 2 seconds for our synchronous decision. This module answers
that question deterministically: approve or decline, with a reason we log.

Decision tree (any fail → decline):
  1. Kill switch on → decline.
  2. Merchant category not in the business's MCC allowlist → decline.
  3. Amount exceeds per-auth cap (default $500) → decline.
  4. Amount + week-to-date spend exceeds weekly cap → decline.
  5. Business is paused / archived → decline.
  Else → approve.

Every decision writes a `spend_authorization_decision` event to the log so
we can audit + reproduce. The Stripe side also enforces the same spending
limits on the card (belt-and-braces); this module adds MCC-awareness and
kill-switch coupling Stripe can't know about.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.db.models import AgentEvent, AgentSession, Business
from helm.services import event_log, kill_switch

# Default MCC allowlist covers what agents legitimately spend on:
# - 5734: Computer Software Stores (SaaS, hosting)
# - 5735: Record Stores (domains, Shopify)
# - 7372: Computer Programming, Data Processing (hosting, SaaS)
# - 7311: Advertising Services (Meta, Google, TikTok)
# - 5812: Eating places (no — excluded deliberately)
# - 5999: Misc retail (suppliers like Printful)
_DEFAULT_MCC_ALLOWLIST: frozenset[str] = frozenset(
    {
        "5734",  # Computer Software
        "5735",  # Record Stores / niche incl. Shopify
        "7372",  # Computer / Data Processing
        "7311",  # Advertising Services
        "5999",  # Misc retail (POD suppliers)
        "4816",  # Computer Network / Information Services
        "4111",  # Transportation passengers — shipping bureau in some cases
        "7399",  # Business Services not elsewhere classified
    }
)


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    approved: bool
    reason: str
    business_id: uuid.UUID | None
    amount_cents: int
    merchant_category: str | None


async def decide_authorization(
    db: AsyncSession,
    *,
    stripe_account_id: str,
    amount_cents: int,
    merchant_category: str | None,
    merchant_name: str | None = None,
    per_auth_cap_cents: int | None = None,
    mcc_allowlist: frozenset[str] = _DEFAULT_MCC_ALLOWLIST,
) -> AuthorizationDecision:
    """Decide a single Stripe authorization. All business lookups by
    stripe_account_id. Writes an audit event before returning.

    `per_auth_cap_cents` is optional: when omitted we read the business's
    own cap column. Callers in tests can still inject a hardcoded value.
    """
    # 1. Find the business.
    biz_row = await db.execute(
        select(Business).where(Business.stripe_account_id == stripe_account_id)
    )
    biz = biz_row.scalar_one_or_none()
    if biz is None:
        return await _log_and_return(
            db,
            approved=False,
            reason="no_business_for_stripe_account",
            business_id=None,
            amount_cents=amount_cents,
            merchant_category=merchant_category,
            merchant_name=merchant_name,
        )

    # 2. Kill switch.
    if await kill_switch.is_active(db, biz.user_id):
        return await _log_and_return(
            db,
            approved=False,
            reason="kill_switch_on",
            business_id=biz.id,
            amount_cents=amount_cents,
            merchant_category=merchant_category,
            merchant_name=merchant_name,
        )

    # 3. Business status.
    if biz.status in {"paused", "archived"}:
        return await _log_and_return(
            db,
            approved=False,
            reason=f"business_{biz.status}",
            business_id=biz.id,
            amount_cents=amount_cents,
            merchant_category=merchant_category,
            merchant_name=merchant_name,
        )

    # 4. MCC allowlist. Business-level override wins when set; else default.
    effective_allowlist: frozenset[str] = (
        frozenset(biz.allowed_mcc_codes) if biz.allowed_mcc_codes else mcc_allowlist
    )
    if merchant_category and merchant_category not in effective_allowlist:
        return await _log_and_return(
            db,
            approved=False,
            reason=f"mcc_not_allowed:{merchant_category}",
            business_id=biz.id,
            amount_cents=amount_cents,
            merchant_category=merchant_category,
            merchant_name=merchant_name,
        )

    # 5. Per-auth cap.
    effective_per_auth_cap = (
        per_auth_cap_cents if per_auth_cap_cents is not None else biz.per_auth_cap_cents
    )
    if amount_cents > effective_per_auth_cap:
        return await _log_and_return(
            db,
            approved=False,
            reason=f"per_auth_cap_exceeded:{amount_cents}>{effective_per_auth_cap}",
            business_id=biz.id,
            amount_cents=amount_cents,
            merchant_category=merchant_category,
            merchant_name=merchant_name,
        )

    # 6. Weekly cap.
    week_ago = datetime.now(UTC) - timedelta(days=7)
    spent_q = await db.execute(
        select(func.coalesce(func.sum(AgentEvent.cost_cents), 0)).where(
            AgentEvent.business_id == biz.id,
            AgentEvent.event_type == "spend_authorized",
            AgentEvent.created_at >= week_ago,
        )
    )
    spent = int(spent_q.scalar() or 0)
    if spent + amount_cents > biz.weekly_spend_cap_cents:
        return await _log_and_return(
            db,
            approved=False,
            reason=(f"weekly_cap_would_exceed:{spent}+{amount_cents}>{biz.weekly_spend_cap_cents}"),
            business_id=biz.id,
            amount_cents=amount_cents,
            merchant_category=merchant_category,
            merchant_name=merchant_name,
        )

    # All checks passed. Approve and log with amount on cost_cents so it
    # counts toward the weekly running total going forward.
    return await _log_and_return(
        db,
        approved=True,
        reason="approved",
        business_id=biz.id,
        amount_cents=amount_cents,
        merchant_category=merchant_category,
        merchant_name=merchant_name,
    )


async def _log_and_return(
    db: AsyncSession,
    *,
    approved: bool,
    reason: str,
    business_id: uuid.UUID | None,
    amount_cents: int,
    merchant_category: str | None,
    merchant_name: str | None,
) -> AuthorizationDecision:
    # Latest agent session on this business (or user-level if biz unknown).
    session_id = await _latest_session(db, business_id)

    if session_id is not None:
        await event_log.write(
            db,
            session_id=session_id,
            business_id=business_id,
            event_type="spend_authorized" if approved else "spend_declined",
            agent_name="stripe_authorization",
            payload={
                "reason": reason,
                "amount_cents": amount_cents,
                "merchant_category": merchant_category,
                "merchant_name": merchant_name,
            },
            cost_cents=amount_cents if approved else 0,
        )

    return AuthorizationDecision(
        approved=approved,
        reason=reason,
        business_id=business_id,
        amount_cents=amount_cents,
        merchant_category=merchant_category,
    )


async def _latest_session(db: AsyncSession, business_id: uuid.UUID | None) -> uuid.UUID | None:
    """Best-effort: an agent session to attribute this event to. If we can't
    find one, we still decide — we just skip the event-log write."""
    if business_id is None:
        return None
    # Prefer a session scoped to this business; fall back to any user-level
    # session for the business's owner.
    res = await db.execute(
        select(AgentSession.id)
        .join(Business, Business.id == business_id)
        .where(
            (AgentSession.business_id == business_id) | (AgentSession.user_id == Business.user_id)
        )
        .order_by(AgentSession.last_active_at.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()

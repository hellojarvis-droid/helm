"""Billing — tier + usage surface for clients.

GET /billing/me returns the user's current tier + its limits + their
current usage against those limits (e.g., 2/3 businesses used). Clients
render this on a /billing settings page and on the sign-up / upgrade CTA.

Stripe Checkout + subscription webhooks land in a later session; this
first cut enforces tier caps at write-time and lets the client show the
state without needing Stripe configured.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.models import AgentEvent, Business
from helm.db.session import get_session
from helm.services import tier_limits
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(prefix="/billing", tags=["billing"])


class BillingState(BaseModel):
    tier: str
    display_name: str
    max_businesses: int  # 0 = unlimited
    monthly_tokens: int  # 0 = unlimited
    businesses_used: int
    # LLM tokens implied by cost_cents — rough only; exact usage tracking
    # comes with Stripe metered pricing in a later session.
    month_to_date_cost_cents: int


@router.get("/me", response_model=BillingState)
async def get_billing(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> BillingState:
    user_row = await sync_user_from_supabase(db, user)
    limits = tier_limits.get_limits(user_row.tier)

    biz_q = await db.execute(
        select(func.count()).select_from(Business).where(Business.user_id == user_row.id)
    )
    businesses_used = int(biz_q.scalar() or 0)

    # Sum LLM-attributable cost_cents (message.agent events) across the
    # current calendar-month window on this user's businesses. Tokens are
    # not directly stored; we report cost as a rough proxy.
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Approximate: last 30d if we're early in the month avoids edge cases.
    window_since = min(month_start, datetime.now(UTC) - timedelta(days=1))
    cost_q = await db.execute(
        select(func.coalesce(func.sum(AgentEvent.cost_cents), 0))
        .select_from(AgentEvent)
        .join(Business, Business.id == AgentEvent.business_id)
        .where(
            Business.user_id == user_row.id,
            AgentEvent.event_type == "message.agent",
            AgentEvent.created_at >= window_since,
        )
    )
    cost_cents = int(cost_q.scalar() or 0)

    return BillingState(
        tier=user_row.tier,
        display_name=limits.display_name,
        max_businesses=limits.max_businesses,
        monthly_tokens=limits.monthly_tokens,
        businesses_used=businesses_used,
        month_to_date_cost_cents=cost_cents,
    )

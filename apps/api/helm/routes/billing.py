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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.config import get_settings
from helm.db.models import AgentEvent, Business
from helm.db.session import get_session
from helm.services import stripe_billing, tier_limits
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
    subscription_status: str


class CheckoutRequest(BaseModel):
    target_tier: str  # 'founder' | 'operator' | 'portfolio'


class CheckoutResponse(BaseModel):
    url: str


class PortalResponse(BaseModel):
    url: str


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
        subscription_status=user_row.subscription_status,
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def start_checkout(
    body: CheckoutRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> CheckoutResponse:
    """Create a Stripe Checkout Session for the target tier. Returns the URL
    the client redirects to. Webhook (customer.subscription.created) flips
    the user's tier + subscription fields once payment succeeds.
    """
    settings = get_settings()
    price_map = {
        "founder": settings.stripe_price_founder,
        "operator": settings.stripe_price_operator,
        "portfolio": settings.stripe_price_portfolio,
    }
    price_id = price_map.get(body.target_tier)
    if not price_id:
        raise HTTPException(
            status_code=400,
            detail=f"no Stripe price configured for tier '{body.target_tier}'",
        )

    user_row = await sync_user_from_supabase(db, user)
    customer_id = await stripe_billing.get_or_create_customer(
        user_id=str(user_row.id),
        email=user_row.email,
        existing=user_row.stripe_customer_id,
    )
    if user_row.stripe_customer_id != customer_id:
        user_row.stripe_customer_id = customer_id
        await db.commit()

    try:
        url = await stripe_billing.create_checkout_session(
            customer_id=customer_id,
            price_id=price_id,
            success_url=settings.billing_success_url,
            cancel_url=settings.billing_cancel_url,
        )
    except Exception as e:  # surface as 502 so the client can retry
        raise HTTPException(status_code=502, detail=f"stripe checkout failed: {e}") from e

    return CheckoutResponse(url=url)


@router.post("/portal", response_model=PortalResponse)
async def open_portal(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> PortalResponse:
    """Open the Stripe Customer Portal so the user can manage their
    subscription (change plan, update payment method, cancel, view invoices).
    Requires a Stripe customer — created automatically on first /checkout.
    """
    user_row = await sync_user_from_supabase(db, user)
    if not user_row.stripe_customer_id:
        raise HTTPException(
            status_code=409,
            detail="no Stripe customer yet — upgrade via /billing/checkout first",
        )
    settings = get_settings()
    try:
        url = await stripe_billing.create_portal_session(
            customer_id=user_row.stripe_customer_id,
            return_url=settings.billing_success_url,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"stripe portal failed: {e}") from e
    return PortalResponse(url=url)

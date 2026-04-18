"""Businesses REST endpoints.

Thin CRUD on top of `helm.db.tenant` helpers so every query is tenant-scoped
by construction. Create/list/detail for Phase 1; update/archive land alongside
pause/resume in a later session.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.config import get_settings
from helm.db.models import AgentEvent, Business
from helm.db.session import get_session
from helm.db.tenant import get_business_for_user, list_businesses_for_user
from helm.services import stripe_client
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(prefix="/businesses", tags=["businesses"])


VERTICALS = {"dtc_physical", "dtc_pod", "saas", "services"}


class CreateBusinessRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    vertical: Annotated[str, Field(description="One of " + ", ".join(sorted(VERTICALS)))]
    weekly_spend_cap_cents: Annotated[
        int,
        Field(
            default=50000,
            ge=0,
            le=10_000_000,
            description="Hard weekly cap the Stripe Issuing card enforces.",
        ),
    ] = 50000


class BusinessResponse(BaseModel):
    id: uuid.UUID
    name: str
    vertical: str
    status: str
    stripe_account_id: str | None
    stripe_card_id: str | None
    shopify_shop_domain: str | None
    weekly_spend_cap_cents: int
    per_auth_cap_cents: int
    allowed_mcc_codes: list[str] | None
    brand_kit: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    stripe_sync: dict[str, Any] | None = None

    @classmethod
    def from_row(cls, row: Business, stripe_sync: dict[str, Any] | None = None) -> BusinessResponse:
        return cls(
            id=row.id,
            name=row.name,
            vertical=row.vertical,
            status=row.status,
            stripe_account_id=row.stripe_account_id,
            stripe_card_id=row.stripe_card_id,
            shopify_shop_domain=row.shopify_shop_domain,
            weekly_spend_cap_cents=row.weekly_spend_cap_cents,
            per_auth_cap_cents=row.per_auth_cap_cents,
            allowed_mcc_codes=row.allowed_mcc_codes,
            brand_kit=row.brand_kit,
            created_at=row.created_at,
            updated_at=row.updated_at,
            stripe_sync=stripe_sync,
        )


class UpdateBusinessRequest(BaseModel):
    weekly_spend_cap_cents: Annotated[int, Field(ge=0, le=10_000_000)] | None = None
    per_auth_cap_cents: Annotated[int, Field(ge=0, le=10_000_000)] | None = None
    # List means "override the default allowlist with this set". Explicit
    # empty list [] means "allow nothing" (effectively locks the card).
    # To restore the default, the client sends null / omits the field via a
    # different sentinel — see patch handler.
    allowed_mcc_codes: list[str] | None = None
    # Sentinel: when true, reset allowed_mcc_codes to NULL (i.e., back to the
    # default allowlist). Distinct from passing null above (which leaves the
    # field unset, not reset).
    reset_mcc_codes_to_default: bool = False


@router.post("", response_model=BusinessResponse, status_code=201)
async def create_business(
    body: CreateBusinessRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> BusinessResponse:
    if body.vertical not in VERTICALS:
        raise HTTPException(status_code=422, detail=f"vertical must be one of {sorted(VERTICALS)}")
    user_row = await sync_user_from_supabase(db, user)
    biz = Business(
        user_id=user_row.id,
        name=body.name,
        vertical=body.vertical,
        weekly_spend_cap_cents=body.weekly_spend_cap_cents,
        status="initializing",
    )
    db.add(biz)
    await db.commit()
    await db.refresh(biz)
    return BusinessResponse.from_row(biz)


@router.get("", response_model=list[BusinessResponse])
async def list_businesses(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[BusinessResponse]:
    user_row = await sync_user_from_supabase(db, user)
    rows = await list_businesses_for_user(db, user_row.id)
    return [BusinessResponse.from_row(r) for r in rows]


@router.get("/{business_id}", response_model=BusinessResponse)
async def get_business(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> BusinessResponse:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        # Fail closed — don't leak "exists but not yours" vs "doesn't exist".
        raise HTTPException(status_code=404, detail="business not found")
    return BusinessResponse.from_row(biz)


@router.patch("/{business_id}", response_model=BusinessResponse)
async def update_business(
    business_id: uuid.UUID,
    body: UpdateBusinessRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> BusinessResponse:
    """Update a business's spending caps. Pushes the new limits to Stripe's
    card-level spending_controls when Issuing is enabled AND the card exists,
    so Stripe's own enforcement stays in lockstep with our DB.
    """
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    changed = False
    if body.weekly_spend_cap_cents is not None:
        biz.weekly_spend_cap_cents = body.weekly_spend_cap_cents
        changed = True
    if body.per_auth_cap_cents is not None:
        biz.per_auth_cap_cents = body.per_auth_cap_cents
        changed = True
    if body.reset_mcc_codes_to_default:
        biz.allowed_mcc_codes = None
        changed = True
    elif body.allowed_mcc_codes is not None:
        # Normalize: strip whitespace, dedupe, keep order.
        seen: set[str] = set()
        normalized: list[str] = []
        for code in body.allowed_mcc_codes:
            c = code.strip()
            if c and c not in seen:
                seen.add(c)
                normalized.append(c)
        biz.allowed_mcc_codes = normalized
        changed = True
    if not changed:
        return BusinessResponse.from_row(biz)

    stripe_sync: dict[str, Any] = {"attempted": False}
    settings = get_settings()
    if settings.stripe_issuing_enabled and biz.stripe_card_id and biz.stripe_account_id:
        stripe_sync["attempted"] = True
        try:
            await stripe_client.update_issuing_caps(
                account_id=biz.stripe_account_id,
                card_id=biz.stripe_card_id,
                weekly_spend_cap_cents=biz.weekly_spend_cap_cents,
                per_auth_cap_cents=biz.per_auth_cap_cents,
                allowed_mcc_codes=biz.allowed_mcc_codes,
            )
            stripe_sync["synced"] = True
        except Exception as e:  # surface sync failure to client
            stripe_sync["synced"] = False
            stripe_sync["error"] = str(e)[:200]

    await db.commit()
    await db.refresh(biz)
    return BusinessResponse.from_row(biz, stripe_sync=stripe_sync)


class EventResponse(BaseModel):
    id: int
    session_id: uuid.UUID
    business_id: uuid.UUID | None
    event_type: str
    agent_name: str
    payload: dict[str, Any]
    cost_cents: int
    created_at: datetime

    @classmethod
    def from_row(cls, row: AgentEvent) -> EventResponse:
        return cls(
            id=row.id,
            session_id=row.session_id,
            business_id=row.business_id,
            event_type=row.event_type,
            agent_name=row.agent_name,
            payload=row.payload,
            cost_cents=row.cost_cents,
            created_at=row.created_at,
        )


class SpendSummary(BaseModel):
    weekly_cap_cents: int
    week_to_date_cents: int
    remaining_cents: int
    llm_cost_cents: int
    declined_count: int
    revenue_wtd_cents: int
    net_wtd_cents: int
    window_days: int
    since: datetime


@router.get("/{business_id}/spend", response_model=SpendSummary)
async def get_spend(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> SpendSummary:
    """Spend dashboard data for the last 7 days.

    - week_to_date_cents: what the business actually spent (Stripe authorizations
      approved). This is the metric the weekly cap gates against.
    - llm_cost_cents: inference cost of running the agents over the same window.
      Not gated by the spend cap; reported separately so the user sees both.
    - declined_count: spend_declined events in the window — a signal the agents
      hit a policy or budget wall.
    """
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    since = datetime.now(UTC) - timedelta(days=7)

    wtd_q = await db.execute(
        select(func.coalesce(func.sum(AgentEvent.cost_cents), 0)).where(
            AgentEvent.business_id == business_id,
            AgentEvent.event_type == "spend_authorized",
            AgentEvent.created_at >= since,
        )
    )
    wtd = int(wtd_q.scalar() or 0)

    llm_q = await db.execute(
        select(func.coalesce(func.sum(AgentEvent.cost_cents), 0)).where(
            AgentEvent.business_id == business_id,
            AgentEvent.event_type == "message.agent",
            AgentEvent.created_at >= since,
        )
    )
    llm = int(llm_q.scalar() or 0)

    declined_q = await db.execute(
        select(func.count()).where(
            AgentEvent.business_id == business_id,
            AgentEvent.event_type == "spend_declined",
            AgentEvent.created_at >= since,
        )
    )
    declined = int(declined_q.scalar() or 0)

    # Revenue — payment_intent.succeeded webhook writes cost_cents as the
    # negative inflow. Sum and flip sign to report positive revenue.
    rev_q = await db.execute(
        select(func.coalesce(func.sum(AgentEvent.cost_cents), 0)).where(
            AgentEvent.business_id == business_id,
            AgentEvent.event_type == "revenue_received",
            AgentEvent.created_at >= since,
        )
    )
    revenue = -int(rev_q.scalar() or 0)

    return SpendSummary(
        weekly_cap_cents=biz.weekly_spend_cap_cents,
        week_to_date_cents=wtd,
        remaining_cents=max(biz.weekly_spend_cap_cents - wtd, 0),
        llm_cost_cents=llm,
        declined_count=declined,
        revenue_wtd_cents=revenue,
        net_wtd_cents=revenue - wtd,
        window_days=7,
        since=since,
    )


@router.get("/{business_id}/events", response_model=list[EventResponse])
async def list_events(
    business_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before_id: int | None = None,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[EventResponse]:
    """Surface the event-sourced record of every agent action on this business.

    Cursor-paginated by `id` (DESC) — pass `before_id` from the last row of
    the previous page to load older events. This backs the "Activity" feed
    on web + mobile so CLAUDE.md hard rule #4 ("user can replay any decision")
    is visible, not just stored.
    """
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    q = select(AgentEvent).where(AgentEvent.business_id == business_id)
    if before_id is not None:
        q = q.where(AgentEvent.id < before_id)
    q = q.order_by(AgentEvent.id.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [EventResponse.from_row(r) for r in rows]

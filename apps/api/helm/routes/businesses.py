"""Businesses REST endpoints.

Thin CRUD on top of `helm.db.tenant` helpers so every query is tenant-scoped
by construction. Create/list/detail for Phase 1; update/archive land alongside
pause/resume in a later session.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.models import AgentEvent, Business
from helm.db.session import get_session
from helm.db.tenant import get_business_for_user, list_businesses_for_user
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
    brand_kit: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Business) -> BusinessResponse:
        return cls(
            id=row.id,
            name=row.name,
            vertical=row.vertical,
            status=row.status,
            stripe_account_id=row.stripe_account_id,
            stripe_card_id=row.stripe_card_id,
            shopify_shop_domain=row.shopify_shop_domain,
            weekly_spend_cap_cents=row.weekly_spend_cap_cents,
            brand_kit=row.brand_kit,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


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

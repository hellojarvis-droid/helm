"""Cross-business events endpoint.

`/events` is the tenant-scoped global view of the event log — used by the
web's standalone Events page, the Agents live view, and the Approvals
"Why?" trace. Unlike `/businesses/{id}/events` this doesn't require a
business_id; it returns every event from every business the signed-in user
owns, filterable by `business_id`, `event_type`, `agent_name`, and
`before_id` for cursor pagination.

Tenant isolation is enforced by joining through the `businesses` table
with a user_id filter — a user can never see another user's events even
by spoofing business_ids in query params (the join produces zero rows).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.models import AgentEvent, Business
from helm.db.session import get_session
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(tags=["events"])


class EventResponse(BaseModel):
    id: int
    session_id: uuid.UUID
    business_id: uuid.UUID | None
    event_type: str
    agent_name: str
    payload: dict[str, Any]
    cost_cents: int
    created_at: datetime


@router.get("/events", response_model=list[EventResponse])
async def list_events(
    business_id: uuid.UUID | None = None,
    event_type: Annotated[str | None, Query(max_length=80)] = None,
    agent_name: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before_id: int | None = None,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[EventResponse]:
    """List events across every business the current user owns, newest first.

    Filters stack (AND):
      * business_id  — scope to one business (must be owned by caller)
      * event_type   — exact match (e.g., 'spend_authorized')
      * agent_name   — exact match (e.g., 'ads_operator')
      * before_id    — cursor: only events with id < before_id
    """
    user_row = await sync_user_from_supabase(db, user)

    # Start from AgentEvent joined to Business for tenant scoping. Without
    # the join, a business_id=None event (e.g., top-level CEO session event)
    # would be visible across tenants — we require the business_id join so
    # only events tied to a business the user owns come through.
    q = (
        select(AgentEvent)
        .join(Business, Business.id == AgentEvent.business_id)
        .where(Business.user_id == user_row.id)
    )

    if business_id is not None:
        # Verify ownership explicitly so a 404 vs. 0-results distinction is
        # preserved — users get "business not found" rather than an empty list.
        biz_q = await db.execute(
            select(Business).where(
                Business.id == business_id, Business.user_id == user_row.id
            )
        )
        if biz_q.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="business not found")
        q = q.where(AgentEvent.business_id == business_id)

    if event_type:
        q = q.where(AgentEvent.event_type == event_type)
    if agent_name:
        q = q.where(AgentEvent.agent_name == agent_name)
    if before_id is not None:
        q = q.where(AgentEvent.id < before_id)

    q = q.order_by(AgentEvent.id.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [
        EventResponse(
            id=r.id,
            session_id=r.session_id,
            business_id=r.business_id,
            event_type=r.event_type,
            agent_name=r.agent_name,
            payload=r.payload,
            cost_cents=r.cost_cents,
            created_at=r.created_at,
        )
        for r in rows
    ]

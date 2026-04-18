"""Today — cross-business aggregate for the user's "what's happening now" view.

Used as the landing screen on mobile + web. One endpoint so the client
doesn't need to fan out to /spend + /approvals + /businesses and
client-side reduce.

Window: trailing 24 hours for revenue + spend; pending approvals are
current state (not windowed).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.models import AgentEvent, Approval, Business
from helm.db.session import get_session
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(prefix="/users/me", tags=["today"])


class BusinessToday(BaseModel):
    id: str
    name: str
    vertical: str
    status: str
    revenue_today_cents: int
    spend_today_cents: int
    net_today_cents: int
    pending_approval_count: int


class TodaySummary(BaseModel):
    revenue_today_cents: int
    spend_today_cents: int
    net_today_cents: int
    pending_approval_count: int
    window_hours: int
    since: datetime
    businesses: list[BusinessToday]


@router.get("/today", response_model=TodaySummary)
async def get_today(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> TodaySummary:
    user_row = await sync_user_from_supabase(db, user)
    since = datetime.now(UTC) - timedelta(hours=24)

    # One query each: revenue, spend, pending approvals — grouped by business.
    biz_rows = (
        (await db.execute(select(Business).where(Business.user_id == user_row.id))).scalars().all()
    )
    biz_ids = [b.id for b in biz_rows]

    revenue_by_biz: dict[str, int] = {}
    spend_by_biz: dict[str, int] = {}
    approvals_by_biz: dict[str, int] = {}

    if biz_ids:
        rev_q = await db.execute(
            select(
                AgentEvent.business_id,
                func.coalesce(func.sum(AgentEvent.cost_cents), 0),
            )
            .where(
                AgentEvent.business_id.in_(biz_ids),
                AgentEvent.event_type == "revenue_received",
                AgentEvent.created_at >= since,
            )
            .group_by(AgentEvent.business_id)
        )
        for bid, total in rev_q.all():
            revenue_by_biz[str(bid)] = -int(total or 0)  # flipped — negative was inflow

        sp_q = await db.execute(
            select(
                AgentEvent.business_id,
                func.coalesce(func.sum(AgentEvent.cost_cents), 0),
            )
            .where(
                AgentEvent.business_id.in_(biz_ids),
                AgentEvent.event_type == "spend_authorized",
                AgentEvent.created_at >= since,
            )
            .group_by(AgentEvent.business_id)
        )
        for bid, total in sp_q.all():
            spend_by_biz[str(bid)] = int(total or 0)

        ap_q = await db.execute(
            select(Approval.business_id, func.count())
            .where(
                Approval.business_id.in_(biz_ids),
                Approval.status == "pending",
            )
            .group_by(Approval.business_id)
        )
        for bid, count in ap_q.all():
            approvals_by_biz[str(bid)] = int(count or 0)

    businesses: list[BusinessToday] = []
    total_revenue = 0
    total_spend = 0
    total_pending = 0
    for b in biz_rows:
        key = str(b.id)
        rev = revenue_by_biz.get(key, 0)
        sp = spend_by_biz.get(key, 0)
        pend = approvals_by_biz.get(key, 0)
        total_revenue += rev
        total_spend += sp
        total_pending += pend
        businesses.append(
            BusinessToday(
                id=key,
                name=b.name,
                vertical=b.vertical,
                status=b.status,
                revenue_today_cents=rev,
                spend_today_cents=sp,
                net_today_cents=rev - sp,
                pending_approval_count=pend,
            )
        )

    return TodaySummary(
        revenue_today_cents=total_revenue,
        spend_today_cents=total_spend,
        net_today_cents=total_revenue - total_spend,
        pending_approval_count=total_pending,
        window_hours=24,
        since=since,
        businesses=businesses,
    )

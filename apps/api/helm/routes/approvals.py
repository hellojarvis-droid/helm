"""Approvals REST endpoints.

The CEO Agent produces approval cards via `request_user_approval`; the user
responds here. Response writes an `approval_approved` / `approval_denied` /
`approval_modified` event so the CEO can see it on the next turn via
`query_event_log`.

When the user taps "approve & raise cap" on a spend approval we also bump
the business's weekly_spend_cap_cents AND push the new limit to Stripe's
card-level spending_controls so the authorization flow stays consistent.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.config import get_settings
from helm.db.models import AgentEvent, AgentSession, Approval, Business
from helm.db.session import get_session
from helm.services import event_log, stripe_client
from helm.services.user_sync import sync_user_from_supabase

# Headroom applied when the user approves a spend AND elects to raise the
# weekly cap — the new cap covers week-to-date + the pending spend + this
# buffer so the agent isn't immediately at the ceiling again.
_RAISE_CAP_BUFFER_CENTS = 10_000  # $100

router = APIRouter(prefix="/approvals", tags=["approvals"])

ResponseStatus = Literal["approved", "denied", "modified"]


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    kind: str
    summary: str
    details: dict[str, Any]
    status: str
    requested_at: datetime
    responded_at: datetime | None
    expires_at: datetime
    # Only populated when the user chose "approve & raise cap" on a spend
    # approval and the cap actually changed. Present on /respond responses;
    # null on list/get to keep the surface stable.
    cap_raise: dict[str, Any] | None = None

    @classmethod
    def from_row(cls, row: Approval, cap_raise: dict[str, Any] | None = None) -> ApprovalResponse:
        return cls(
            id=row.id,
            business_id=row.business_id,
            kind=row.kind,
            summary=row.summary,
            details=row.details,
            status=row.status,
            requested_at=row.requested_at,
            responded_at=row.responded_at,
            expires_at=row.expires_at,
            cap_raise=cap_raise,
        )


class RespondRequest(BaseModel):
    status: Annotated[ResponseStatus, Field(description="approved | denied | modified")]
    modifications: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Only used for status='modified'. Free-form dict the CEO reads on next turn "
            "to adjust the plan (e.g. {'max_spend': 200})."
        ),
    )


async def _user_owns_approval(db: AsyncSession, user_id: uuid.UUID, approval: Approval) -> bool:
    """Approvals are business-scoped; ownership is via business.user_id."""
    res = await db.execute(select(Business).where(Business.id == approval.business_id))
    biz = res.scalar_one_or_none()
    return biz is not None and biz.user_id == user_id


async def _expire_lazily(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Flip every pending approval on this user's businesses that's past its
    expires_at to status='expired'. Lazy sweep — we have no scheduler today,
    so read paths trigger cleanup. Returns the number of rows flipped.
    """
    from sqlalchemy import update

    now = datetime.now(UTC)
    # Find the ids first so we can count + short-circuit without a commit.
    stale_ids_q = await db.execute(
        select(Approval.id)
        .join(Business, Business.id == Approval.business_id)
        .where(
            Business.user_id == user_id,
            Approval.status == "pending",
            Approval.expires_at < now,
        )
    )
    stale_ids = list(stale_ids_q.scalars().all())
    if not stale_ids:
        return 0
    await db.execute(
        update(Approval)
        .where(Approval.id.in_(stale_ids))
        .values(status="expired", responded_at=now)
    )
    await db.commit()
    return len(stale_ids)


@router.get("", response_model=list[ApprovalResponse])
async def list_approvals(
    status: str | None = None,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[ApprovalResponse]:
    user_row = await sync_user_from_supabase(db, user)
    await _expire_lazily(db, user_row.id)

    stmt = (
        select(Approval)
        .join(Business, Business.id == Approval.business_id)
        .where(Business.user_id == user_row.id)
        .order_by(Approval.requested_at.desc())
    )
    if status:
        stmt = stmt.where(Approval.status == status)
    res = await db.execute(stmt)
    return [ApprovalResponse.from_row(r) for r in res.scalars().all()]


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(
    approval_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> ApprovalResponse:
    user_row = await sync_user_from_supabase(db, user)
    await _expire_lazily(db, user_row.id)

    res = await db.execute(select(Approval).where(Approval.id == approval_id))
    row = res.scalar_one_or_none()
    if row is None or not await _user_owns_approval(db, user_row.id, row):
        raise HTTPException(status_code=404, detail="approval not found")
    return ApprovalResponse.from_row(row)


@router.post("/{approval_id}/respond", response_model=ApprovalResponse)
async def respond(
    approval_id: uuid.UUID,
    body: RespondRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> ApprovalResponse:
    user_row = await sync_user_from_supabase(db, user)
    res = await db.execute(select(Approval).where(Approval.id == approval_id))
    row = res.scalar_one_or_none()
    if row is None or not await _user_owns_approval(db, user_row.id, row):
        raise HTTPException(status_code=404, detail="approval not found")

    if row.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"approval already in terminal state: {row.status}",
        )

    if row.expires_at < datetime.now(UTC):
        row.status = "expired"
        row.responded_at = datetime.now(UTC)
        await db.commit()
        raise HTTPException(status_code=410, detail="approval expired before response")

    # Translate the API status into the schema's enum + event type.
    new_status = body.status  # "approved" | "denied" | "modified"
    row.status = new_status
    row.responded_at = datetime.now(UTC)
    if body.modifications:
        row.details = {**row.details, "user_modifications": body.modifications}

    # If the user chose "approve & raise the weekly cap" on a spend approval,
    # bump the business's cap atomically with the approval response. We
    # compute the new cap server-side so the client stays simple and we
    # apply the buffer policy in one place.
    cap_raise_meta: dict[str, Any] | None = None
    if (
        new_status == "modified"
        and body.modifications
        and body.modifications.get("raise_weekly_cap") is True
        and row.kind == "spend"
    ):
        cap_raise_meta = await _apply_cap_raise(db, row)

    await db.commit()
    await db.refresh(row)

    # Log the response on the user's active CEO session so the CEO sees it next turn.
    # Fall back to any latest session if no active one exists.
    sess = await db.execute(
        select(AgentSession)
        .where(AgentSession.user_id == user_row.id)
        .order_by(AgentSession.created_at.desc())
        .limit(1)
    )
    session_row = sess.scalar_one_or_none()
    if session_row is not None:
        event_type = f"approval_{new_status}"
        payload: dict[str, Any] = {
            "approval_id": str(row.id),
            "kind": row.kind,
            "summary": row.summary,
            "modifications": body.modifications,
        }
        if cap_raise_meta is not None:
            payload["cap_raise"] = cap_raise_meta
        await event_log.write(
            db,
            session_id=session_row.id,
            business_id=row.business_id,
            event_type=event_type,
            agent_name="user",
            payload=payload,
        )

    return ApprovalResponse.from_row(row, cap_raise=cap_raise_meta)


async def _apply_cap_raise(db: AsyncSession, approval: Approval) -> dict[str, Any] | None:
    """Compute and apply a new weekly cap on the approval's business.

    new_cap = max(current_cap, wtd_authorized + pending_amount + buffer)
    The pending spend's amount comes from approval.details.amount_cents; if it's
    missing we skip the raise (nothing to guarantee room for).
    """
    amount = approval.details.get("amount_cents")
    if not isinstance(amount, int) or amount <= 0:
        return None

    biz_row = await db.execute(select(Business).where(Business.id == approval.business_id))
    biz = biz_row.scalar_one_or_none()
    if biz is None:
        return None

    # Mirror stripe_authorization: only spend_authorized inside the last 7 days
    # counts toward week-to-date, so the new cap is sized against real usage.
    since = datetime.now(UTC) - timedelta(days=7)
    wtd_q = await db.execute(
        select(func.coalesce(func.sum(AgentEvent.cost_cents), 0)).where(
            AgentEvent.business_id == biz.id,
            AgentEvent.event_type == "spend_authorized",
            AgentEvent.created_at >= since,
        )
    )
    wtd = int(wtd_q.scalar() or 0)

    required = wtd + amount + _RAISE_CAP_BUFFER_CENTS
    new_cap = max(biz.weekly_spend_cap_cents, required)
    old_cap = biz.weekly_spend_cap_cents
    if new_cap == old_cap:
        return {
            "old_cap_cents": old_cap,
            "new_cap_cents": new_cap,
            "changed": False,
            "reason": "existing cap already covers wtd + amount + buffer",
        }

    biz.weekly_spend_cap_cents = new_cap

    # Push the new cap to Stripe so the card's own spending_limits match.
    # Without this, the DB cap goes up but the real merchant authorization
    # still declines at Stripe's edge (Stripe enforces the card-level limit
    # independently of our authorization-decision webhook).
    stripe_sync: dict[str, Any] = {"attempted": False}
    settings = get_settings()
    if settings.stripe_issuing_enabled and biz.stripe_card_id and biz.stripe_account_id:
        stripe_sync["attempted"] = True
        try:
            # Mirror both caps + allowlist to Stripe so no knob drifts.
            await stripe_client.update_issuing_caps(
                account_id=biz.stripe_account_id,
                card_id=biz.stripe_card_id,
                weekly_spend_cap_cents=new_cap,
                per_auth_cap_cents=biz.per_auth_cap_cents,
                allowed_mcc_codes=biz.allowed_mcc_codes,
            )
            stripe_sync["synced"] = True
        except Exception as e:
            stripe_sync["synced"] = False
            stripe_sync["error"] = str(e)[:200]

    return {
        "old_cap_cents": old_cap,
        "new_cap_cents": new_cap,
        "changed": True,
        "wtd_cents": wtd,
        "buffer_cents": _RAISE_CAP_BUFFER_CENTS,
        "stripe_sync": stripe_sync,
    }

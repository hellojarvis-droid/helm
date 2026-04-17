"""Approvals REST endpoints.

The CEO Agent produces approval cards via `request_user_approval`; the user
responds here. Response writes an `approval_granted` / `approval_denied` /
`approval_modified` event so the CEO can see it on the next turn via
`query_event_log`.

The connected Stripe card / spend-gate enforcement that consumes an approval
lands in Phase 2 alongside the money spine. For now, the approval flow is
pure audit trail + event log — the CEO sees it, relays to the user.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.models import AgentSession, Approval, Business
from helm.db.session import get_session
from helm.services import event_log
from helm.services.user_sync import sync_user_from_supabase

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

    @classmethod
    def from_row(cls, row: Approval) -> ApprovalResponse:
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


@router.get("", response_model=list[ApprovalResponse])
async def list_approvals(
    status: str | None = None,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[ApprovalResponse]:
    user_row = await sync_user_from_supabase(db, user)
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
        await event_log.write(
            db,
            session_id=session_row.id,
            business_id=row.business_id,
            event_type=event_type,
            agent_name="user",
            payload={
                "approval_id": str(row.id),
                "kind": row.kind,
                "summary": row.summary,
                "modifications": body.modifications,
            },
        )

    return ApprovalResponse.from_row(row)

"""Computer-use escalations REST endpoints.

Two audiences hit these routes:

  * **Desktop worker** — polls the queue, claims a task, heartbeats while
    running, posts a terminal state.
  * **Web/mobile** — list/get for the activity surface, plus a user-initiated
    cancel.

All endpoints are tenant-scoped via `require_user` + ownership filters in the
service layer (see `helm.services.computer_use`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.models import ComputerUseEscalation
from helm.db.session import get_session
from helm.services import computer_use
from helm.services.computer_use import EscalationError
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(prefix="/computer_use", tags=["computer_use"])


class EscalationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    business_id: uuid.UUID
    session_id: uuid.UUID
    status: str
    requester: str
    task: str
    app_hint: str
    result: dict[str, Any]
    error: str | None
    claimed_by: str | None
    claimed_at: datetime | None
    last_heartbeat_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: ComputerUseEscalation) -> EscalationResponse:
        return cls(
            id=row.id,
            user_id=row.user_id,
            business_id=row.business_id,
            session_id=row.session_id,
            status=row.status,
            requester=row.requester,
            task=row.task,
            app_hint=row.app_hint,
            result=row.result,
            error=row.error,
            claimed_by=row.claimed_by,
            claimed_at=row.claimed_at,
            last_heartbeat_at=row.last_heartbeat_at,
            completed_at=row.completed_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


def _to_http(err: EscalationError) -> HTTPException:
    return HTTPException(status_code=err.http_status, detail=str(err))


@router.get("", response_model=list[EscalationResponse])
async def list_escalations(
    status: str | None = None,
    business_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[EscalationResponse]:
    """List escalations the user owns. Filter by status or business_id."""
    user_row = await sync_user_from_supabase(db, user)
    statuses = (status,) if status else None
    rows = await computer_use.list_for_user(
        db, user_row.id, statuses=statuses, business_id=business_id, limit=limit
    )
    return [EscalationResponse.from_row(r) for r in rows]


@router.get("/queue", response_model=list[EscalationResponse])
async def queue_for_desktop(
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[EscalationResponse]:
    """Desktop worker entrypoint: 'what's queued or actively-mine to run?'

    Returns queued + claimed + running rows. The desktop should claim() a
    queued one to start working it; rows already claimed/running by this
    desktop come back so the worker can resume after a restart.
    """
    user_row = await sync_user_from_supabase(db, user)
    rows = await computer_use.list_for_user(
        db,
        user_row.id,
        statuses=("queued", "claimed", "running"),
        limit=limit,
    )
    return [EscalationResponse.from_row(r) for r in rows]


@router.get("/{escalation_id}", response_model=EscalationResponse)
async def get_escalation(
    escalation_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> EscalationResponse:
    user_row = await sync_user_from_supabase(db, user)
    row = await computer_use.get_for_user(db, user_row.id, escalation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="escalation not found")
    return EscalationResponse.from_row(row)


class ClaimRequest(BaseModel):
    claimed_by: Annotated[
        str,
        Field(
            min_length=4,
            max_length=128,
            description="Stable device fingerprint, e.g. machine UUID + helm install id.",
        ),
    ]


@router.post("/{escalation_id}/claim", response_model=EscalationResponse)
async def claim_escalation(
    escalation_id: uuid.UUID,
    body: ClaimRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> EscalationResponse:
    user_row = await sync_user_from_supabase(db, user)
    try:
        row = await computer_use.claim(
            db, user_row.id, escalation_id, claimed_by=body.claimed_by
        )
    except EscalationError as e:
        raise _to_http(e) from e
    return EscalationResponse.from_row(row)


class HeartbeatRequest(BaseModel):
    claimed_by: Annotated[str, Field(min_length=4, max_length=128)]
    progress_note: str | None = Field(
        default=None,
        max_length=500,
        description="Optional human-readable progress, written as an event_log row.",
    )


@router.post("/{escalation_id}/heartbeat", response_model=EscalationResponse)
async def heartbeat_escalation(
    escalation_id: uuid.UUID,
    body: HeartbeatRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> EscalationResponse:
    user_row = await sync_user_from_supabase(db, user)
    try:
        row = await computer_use.heartbeat(
            db,
            user_row.id,
            escalation_id,
            claimed_by=body.claimed_by,
            progress_note=body.progress_note,
        )
    except EscalationError as e:
        raise _to_http(e) from e
    return EscalationResponse.from_row(row)


class CompleteRequest(BaseModel):
    claimed_by: Annotated[str, Field(min_length=4, max_length=128)]
    status: Literal["succeeded", "failed"]
    result: dict[str, Any] | None = None
    error: str | None = Field(default=None, max_length=2000)


@router.post("/{escalation_id}/complete", response_model=EscalationResponse)
async def complete_escalation(
    escalation_id: uuid.UUID,
    body: CompleteRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> EscalationResponse:
    user_row = await sync_user_from_supabase(db, user)
    try:
        row = await computer_use.complete(
            db,
            user_row.id,
            escalation_id,
            claimed_by=body.claimed_by,
            status=body.status,
            result=body.result,
            error=body.error,
        )
    except EscalationError as e:
        raise _to_http(e) from e
    return EscalationResponse.from_row(row)


class CancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


@router.post("/{escalation_id}/cancel", response_model=EscalationResponse)
async def cancel_escalation(
    escalation_id: uuid.UUID,
    body: CancelRequest | None = None,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> EscalationResponse:
    user_row = await sync_user_from_supabase(db, user)
    try:
        row = await computer_use.cancel(
            db,
            user_row.id,
            escalation_id,
            reason=(body.reason if body else None),
        )
    except EscalationError as e:
        raise _to_http(e) from e
    return EscalationResponse.from_row(row)

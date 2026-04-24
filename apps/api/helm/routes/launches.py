"""Business launch REST + SSE endpoints.

Three surfaces on the launch workflow:

  POST /businesses/{id}/launch  — kick off (idempotent: returns active launch)
  GET  /businesses/{id}/launch  — snapshot (current state + every step)
  GET  /businesses/{id}/launch/stream
                                — SSE feed of transitions for launch theater

The workflow runner itself lives in `helm.services.launch_workflow`; this
module is a thin HTTP layer over it. Authorization uses the same
tenant-scoping as the rest of /businesses.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.models import AgentEvent
from helm.db.session import get_session, session_scope
from helm.db.tenant import get_business_for_user
from helm.services import launch_workflow, sessions
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(prefix="/businesses/{business_id}/launch", tags=["launches"])
log = structlog.get_logger("helm.launches")


class LaunchSnapshotResponse(BaseModel):
    launch_id: str
    business_id: str
    status: str
    current_step: str | None
    started_at: str
    completed_at: str | None
    error: str | None
    steps: list[dict[str, Any]]


@router.post("", response_model=LaunchSnapshotResponse)
async def start_business_launch(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> LaunchSnapshotResponse:
    """Kick off (or resume) a launch. Idempotent — a second POST while a
    launch is active returns the same launch snapshot.
    """
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    # Reuse the user's CEO session so launch events stream into the same log.
    session = await sessions.get_or_create_ceo_session(db, user_row.id)

    try:
        launch = await launch_workflow.start_launch(
            db,
            business_id=business_id,
            user_id=user_row.id,
            session_id=session.id,
        )
    except launch_workflow.LaunchAlreadyActiveError as e:
        snap = await launch_workflow.snapshot(db, e.launch_id)
        if snap is None:  # shouldn't happen; safety net
            raise HTTPException(status_code=409, detail="launch in progress") from e
        # Re-schedule just in case the worker crashed between enqueue and run.
        launch_workflow.schedule_launch(snap.launch_id)
        return LaunchSnapshotResponse(**snap.to_dict())

    launch_workflow.schedule_launch(launch.id)
    snap = await launch_workflow.snapshot(db, launch.id)
    assert snap is not None  # just created
    return LaunchSnapshotResponse(**snap.to_dict())


@router.get("", response_model=LaunchSnapshotResponse)
async def get_latest_launch(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> LaunchSnapshotResponse:
    """Latest launch snapshot for a business (active or most recent)."""
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    snap = await launch_workflow.snapshot_for_business(db, business_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="no launch for this business yet")
    return LaunchSnapshotResponse(**snap.to_dict())


# Event types emitted by the launch workflow — filter SSE feed to these.
_LAUNCH_EVENT_TYPES = (
    "launch_started",
    "launch_step_started",
    "launch_step_completed",
    "launch_step_failed",
    "launch_step_skipped",
    "launch_completed",
    "launch_failed",
    "approval_requested",
)


@router.get("/stream")
async def stream_launch(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """SSE feed of launch transitions. Emits one event per matching
    `agent_events` row, then closes when the launch terminates.

    The client renders each event as a step-card state change; when
    it sees `launch_completed` or `launch_failed`, it can fetch the
    final snapshot via GET /launch and stop listening.
    """
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    # Send an initial snapshot so the client has the current state even for
    # launches already completed before the stream connected.
    initial_snapshot = await launch_workflow.snapshot_for_business(db, business_id)

    async def iter_events() -> AsyncIterator[str]:
        if initial_snapshot is not None:
            yield _sse(
                "snapshot",
                initial_snapshot.to_dict(),
            )
            # If already terminal, short-circuit.
            if initial_snapshot.status in ("completed", "failed", "cancelled"):
                yield _sse("done", {})
                return

        last_event_id = 0
        idle_ticks = 0
        # Cap stream lifetime so connections don't sit forever.
        for _tick in range(600):  # ~10 min at 1s poll
            async with session_scope() as streaming_db:
                q = (
                    select(AgentEvent)
                    .where(
                        AgentEvent.business_id == business_id,
                        AgentEvent.event_type.in_(_LAUNCH_EVENT_TYPES),
                        AgentEvent.id > last_event_id,
                    )
                    .order_by(AgentEvent.id.asc())
                    .limit(50)
                )
                rows = (await streaming_db.execute(q)).scalars().all()
                if rows:
                    idle_ticks = 0
                    for row in rows:
                        last_event_id = int(row.id)
                        yield _sse(
                            row.event_type,
                            {
                                "event_id": row.id,
                                "agent_name": row.agent_name,
                                "payload": row.payload,
                                "created_at": row.created_at.isoformat(),
                            },
                        )
                else:
                    idle_ticks += 1

                # Check if the launch has terminated; if yes, send done + exit.
                snap = await launch_workflow.snapshot_for_business(streaming_db, business_id)
                if snap is not None and snap.status in ("completed", "failed", "cancelled"):
                    yield _sse("snapshot", snap.to_dict())
                    yield _sse("done", {})
                    return

            await asyncio.sleep(1.0 if idle_ticks < 5 else 2.0)

        yield _sse("timeout", {})

    return StreamingResponse(
        iter_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    """Encode one SSE message. Event name uses the agent_events event_type
    so the client can drive UI transitions by switching on it."""
    payload = json.dumps({**data, "kind": event}, default=str)
    return f"event: {event}\ndata: {payload}\n\n"

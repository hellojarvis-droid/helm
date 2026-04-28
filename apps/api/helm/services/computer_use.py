"""Computer-use escalation service.

Escalations are tasks the desktop app's computer-use sandbox needs to run —
"no API exists" work like TikTok small-budget self-serve or supplier portals.
The CEO Agent (or a specialist) calls `escalate_to_computer_use`, which
inserts a row here. The desktop client polls the queue, claims a row, runs
it, and POSTs a terminal state back.

State machine:
    queued ─claim()─→ claimed ─heartbeat(running)─→ running ─complete()─→ succeeded | failed
       │                  │                            │
       └─── cancel() ──────┴────────────────────────────┘──→ cancelled

Stale rows (claimed or running with no heartbeat for >`STALE_AFTER`) are
re-queued lazily on read — desktop crashes shouldn't strand a task forever.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from helm.db.models import Business, ComputerUseEscalation
from helm.services import event_log

STALE_AFTER = timedelta(minutes=5)
TERMINAL_STATES = ("succeeded", "failed", "cancelled")
ACTIVE_STATES = ("queued", "claimed", "running")


class EscalationError(Exception):
    """Raised when a state transition isn't legal."""

    def __init__(self, message: str, *, http_status: int = 409) -> None:
        super().__init__(message)
        self.http_status = http_status


async def create(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    business_id: uuid.UUID,
    session_id: uuid.UUID,
    requester: str,
    task: str,
    app_hint: str,
) -> ComputerUseEscalation:
    """Insert a queued escalation + an audit event in one transaction.

    Caller is responsible for verifying business ownership before calling.
    """
    row = ComputerUseEscalation(
        user_id=user_id,
        business_id=business_id,
        session_id=session_id,
        requester=requester,
        task=task,
        app_hint=app_hint,
        status="queued",
    )
    db.add(row)
    await db.flush()
    await event_log.write(
        db,
        session_id=session_id,
        business_id=business_id,
        event_type="computer_use_requested",
        agent_name=requester,
        payload={
            "escalation_id": str(row.id),
            "task": task,
            "app_hint": app_hint,
        },
        commit=False,
    )
    await db.commit()
    await db.refresh(row)
    return row


async def list_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    statuses: tuple[str, ...] | None = None,
    business_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[ComputerUseEscalation]:
    """Return escalations for a user, optionally filtered by status / business."""
    await _expire_stale_for_user(db, user_id)

    q = select(ComputerUseEscalation).where(ComputerUseEscalation.user_id == user_id)
    if statuses:
        q = q.where(ComputerUseEscalation.status.in_(statuses))
    if business_id is not None:
        q = q.where(ComputerUseEscalation.business_id == business_id)
    q = q.order_by(ComputerUseEscalation.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return list(rows)


async def get_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    escalation_id: uuid.UUID,
) -> ComputerUseEscalation | None:
    """Tenant-scoped fetch — returns None if not owned by user."""
    q = select(ComputerUseEscalation).where(
        ComputerUseEscalation.id == escalation_id,
        ComputerUseEscalation.user_id == user_id,
    )
    return (await db.execute(q)).scalar_one_or_none()


async def claim(
    db: AsyncSession,
    user_id: uuid.UUID,
    escalation_id: uuid.UUID,
    *,
    claimed_by: str,
) -> ComputerUseEscalation:
    """Atomically transition queued→claimed. Returns the updated row.

    `claimed_by` is the desktop's device fingerprint so we can tell if the
    same desktop is reconnecting vs a different one is stealing the task.
    """
    await _expire_stale_for_user(db, user_id)

    now = datetime.now(UTC)
    # Conditional UPDATE — only flips queued rows. Returning the id tells us
    # whether we won the race; another desktop / poll cycle may have grabbed it.
    res = await db.execute(
        update(ComputerUseEscalation)
        .where(
            ComputerUseEscalation.id == escalation_id,
            ComputerUseEscalation.user_id == user_id,
            ComputerUseEscalation.status == "queued",
        )
        .values(
            status="claimed",
            claimed_by=claimed_by,
            claimed_at=now,
            last_heartbeat_at=now,
            updated_at=now,
        )
        .returning(ComputerUseEscalation.id)
    )
    if res.scalar_one_or_none() is None:
        # Either it doesn't exist for this user or it's no longer queued.
        existing = await get_for_user(db, user_id, escalation_id)
        if existing is None:
            raise EscalationError("escalation not found", http_status=404)
        raise EscalationError(
            f"cannot claim: status is {existing.status}", http_status=409
        )
    await db.commit()
    row = await get_for_user(db, user_id, escalation_id)
    assert row is not None
    return row


async def heartbeat(
    db: AsyncSession,
    user_id: uuid.UUID,
    escalation_id: uuid.UUID,
    *,
    claimed_by: str,
    progress_note: str | None = None,
) -> ComputerUseEscalation:
    """Bump last_heartbeat_at. Promotes claimed→running on first heartbeat."""
    row = await get_for_user(db, user_id, escalation_id)
    if row is None:
        raise EscalationError("escalation not found", http_status=404)
    if row.status in TERMINAL_STATES:
        raise EscalationError(
            f"cannot heartbeat: status is {row.status}", http_status=409
        )
    if row.claimed_by != claimed_by:
        raise EscalationError(
            "this device does not own the claim", http_status=409
        )

    now = datetime.now(UTC)
    if row.status == "claimed":
        row.status = "running"
    row.last_heartbeat_at = now

    if progress_note:
        await event_log.write(
            db,
            session_id=row.session_id,
            business_id=row.business_id,
            event_type="computer_use_progress",
            agent_name=row.requester,
            payload={
                "escalation_id": str(row.id),
                "note": progress_note[:500],
            },
            commit=False,
        )
    await db.commit()
    await db.refresh(row)
    return row


async def complete(
    db: AsyncSession,
    user_id: uuid.UUID,
    escalation_id: uuid.UUID,
    *,
    claimed_by: str,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> ComputerUseEscalation:
    """Terminal transition. status must be 'succeeded' or 'failed'."""
    if status not in ("succeeded", "failed"):
        raise EscalationError(
            "complete status must be succeeded or failed", http_status=422
        )

    row = await get_for_user(db, user_id, escalation_id)
    if row is None:
        raise EscalationError("escalation not found", http_status=404)
    if row.status in TERMINAL_STATES:
        raise EscalationError(
            f"already terminal: {row.status}", http_status=409
        )
    if row.claimed_by != claimed_by:
        raise EscalationError(
            "this device does not own the claim", http_status=409
        )

    now = datetime.now(UTC)
    row.status = status
    row.result = result or {}
    row.error = error
    row.completed_at = now

    event_type = "computer_use_succeeded" if status == "succeeded" else "computer_use_failed"
    payload: dict[str, Any] = {
        "escalation_id": str(row.id),
        "task": row.task[:500],
        "app_hint": row.app_hint,
    }
    if status == "succeeded":
        # Truncate result for the event-log payload — full result stays on the row.
        payload["result_preview"] = _preview_result(row.result)
    else:
        payload["error"] = (error or "")[:500]

    await event_log.write(
        db,
        session_id=row.session_id,
        business_id=row.business_id,
        event_type=event_type,
        agent_name=row.requester,
        payload=payload,
        commit=False,
    )
    await db.commit()
    await db.refresh(row)
    return row


async def cancel(
    db: AsyncSession,
    user_id: uuid.UUID,
    escalation_id: uuid.UUID,
    *,
    reason: str | None = None,
) -> ComputerUseEscalation:
    """User-initiated cancel. Legal from any non-terminal state."""
    row = await get_for_user(db, user_id, escalation_id)
    if row is None:
        raise EscalationError("escalation not found", http_status=404)
    if row.status in TERMINAL_STATES:
        raise EscalationError(
            f"already terminal: {row.status}", http_status=409
        )

    now = datetime.now(UTC)
    row.status = "cancelled"
    row.completed_at = now
    if reason:
        row.error = reason[:500]

    await event_log.write(
        db,
        session_id=row.session_id,
        business_id=row.business_id,
        event_type="computer_use_cancelled",
        agent_name="user",
        payload={
            "escalation_id": str(row.id),
            "reason": (reason or "")[:200],
        },
        commit=False,
    )
    await db.commit()
    await db.refresh(row)
    return row


async def _expire_stale_for_user(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Re-queue claimed/running rows whose last heartbeat is too old.

    Lazy sweep — we have no scheduler today. Read paths trigger cleanup so a
    desktop that crashed mid-task doesn't strand the escalation forever.
    """
    cutoff = datetime.now(UTC) - STALE_AFTER
    res = await db.execute(
        update(ComputerUseEscalation)
        .where(
            ComputerUseEscalation.user_id == user_id,
            ComputerUseEscalation.status.in_(("claimed", "running")),
            ComputerUseEscalation.last_heartbeat_at < cutoff,
        )
        .values(
            status="queued",
            claimed_by=None,
            claimed_at=None,
            last_heartbeat_at=None,
            updated_at=datetime.now(UTC),
        )
        .returning(ComputerUseEscalation.id)
    )
    rows = list(res.scalars().all())
    if rows:
        await db.commit()
    return len(rows)


async def assert_business_owned(
    db: AsyncSession,
    user_id: uuid.UUID,
    business_id: uuid.UUID,
) -> bool:
    """Fast ownership check used by the tool path (which already holds the
    user's CEO session context but receives the business id from the model)."""
    res = await db.execute(
        select(Business.id).where(
            Business.id == business_id,
            Business.user_id == user_id,
        )
    )
    return res.scalar_one_or_none() is not None


def _preview_result(result: dict[str, Any]) -> dict[str, Any]:
    """Cap each value to 200 chars so a chatty result doesn't bloat the event log."""
    out: dict[str, Any] = {}
    for k, v in list(result.items())[:10]:
        if isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + "…"
        else:
            out[k] = v
    return out

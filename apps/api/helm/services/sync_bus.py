"""Bidirectional sync bus — one primitive for every outbound + inbound
state mirror between Helm and an external system.

How it works:

  1. A module registers a `SyncEntity` describing one kind of mirrored
     state: `stripe_card_caps`, `shopify_product`, `connection_status`.
  2. On a Helm-side mutation, the caller invokes `push(entity_type,
     external_id, ...)`. The bus runs the entity's `push_fn`, logs the
     result to `sync_records`, and returns a `SyncOutcome`.
  3. On an inbound webhook, the receiver invokes `pull(entity_type,
     external_id, ...)`. The bus runs the `pull_fn`, but only if the
     external event's timestamp is strictly after the last Helm-side
     mutation — Helm wins on ties and on stale events.

Conflict resolution is deliberately simple: Helm's `local_updated_at`
wins. A stale pull writes `last_status='conflict'` so the UI can
surface a diff banner, but it does NOT overwrite Helm's state.

Handler signature:

    async def push_fn(db, ctx: PushContext) -> PushResult
    async def pull_fn(db, ctx: PullContext) -> PullResult

Callers use the thin `push()` / `pull()` wrappers below; handlers never
touch the `sync_records` table directly.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.db.models import AgentSession, SyncRecord
from helm.services import event_log

log = structlog.get_logger("helm.sync_bus")


# ────────────────────────────────────────────────────────────────
# Public types
# ────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class PushContext:
    entity_type: str
    external_id: str
    business_id: uuid.UUID | None
    user_id: uuid.UUID | None
    payload: dict[str, Any]


@dataclass(slots=True)
class PullContext:
    entity_type: str
    external_id: str
    business_id: uuid.UUID | None
    user_id: uuid.UUID | None
    external_updated_at: datetime
    payload: dict[str, Any]


@dataclass(slots=True)
class SyncOutcome:
    direction: str  # 'push' | 'pull'
    status: str  # 'ok' | 'failed' | 'conflict'
    error: str | None = None
    record_id: uuid.UUID | None = None
    detail: dict[str, Any] = field(default_factory=dict)


PushFn = Callable[[AsyncSession, PushContext], Awaitable[dict[str, Any]]]
PullFn = Callable[[AsyncSession, PullContext], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class SyncEntity:
    entity_type: str
    push_fn: PushFn | None = None
    pull_fn: PullFn | None = None


_registry: dict[str, SyncEntity] = {}


def register(entity: SyncEntity) -> None:
    _registry[entity.entity_type] = entity


def get(entity_type: str) -> SyncEntity | None:
    return _registry.get(entity_type)


# ────────────────────────────────────────────────────────────────
# Push / pull
# ────────────────────────────────────────────────────────────────


async def push(
    db: AsyncSession,
    *,
    entity_type: str,
    external_id: str,
    business_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> SyncOutcome:
    """Run the outbound handler for an entity and journal the result.

    Always advances `local_updated_at` so a subsequent inbound event with
    an older timestamp is recognized as stale.
    """
    entity = _registry.get(entity_type)
    if entity is None or entity.push_fn is None:
        return SyncOutcome(
            direction="push",
            status="failed",
            error=f"no push handler registered for '{entity_type}'",
        )

    ctx = PushContext(
        entity_type=entity_type,
        external_id=external_id,
        business_id=business_id,
        user_id=user_id,
        payload=payload or {},
    )
    record = await _upsert_record(
        db,
        entity_type=entity_type,
        external_id=external_id,
        business_id=business_id,
        user_id=user_id,
    )
    # Advance the local watermark up-front so a webhook racing with our
    # own push sees the new local time and recognizes its older timestamp
    # as stale. Even if push_fn fails, this is still correct — the user
    # intent was committed on our side at this moment.
    record.local_updated_at = datetime.now(UTC)
    record.last_direction = "push"

    try:
        detail = await entity.push_fn(db, ctx)
        record.last_status = "ok"
        record.last_error = None
        record.payload = {**record.payload, "last_push": detail}
        await db.commit()
        log.info("sync.push_ok", entity=entity_type, external_id=external_id)
        await _emit_sync_event(
            db,
            business_id=business_id,
            direction="push",
            status="ok",
            entity_type=entity_type,
            external_id=external_id,
            detail=detail,
        )
        return SyncOutcome(
            direction="push",
            status="ok",
            record_id=record.id,
            detail=detail,
        )
    except Exception as e:
        err = str(e)[:500]
        record.last_status = "failed"
        record.last_error = err
        await db.commit()
        log.warning("sync.push_failed", entity=entity_type, err=err)
        await _emit_sync_event(
            db,
            business_id=business_id,
            direction="push",
            status="failed",
            entity_type=entity_type,
            external_id=external_id,
            detail={"error": err},
        )
        return SyncOutcome(
            direction="push",
            status="failed",
            error=err,
            record_id=record.id,
        )


async def pull(
    db: AsyncSession,
    *,
    entity_type: str,
    external_id: str,
    external_updated_at: datetime,
    business_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> SyncOutcome:
    """Run the inbound handler for an entity, enforcing Helm-wins semantics.

    If the external event's timestamp is earlier than our last Helm-side
    push, the handler is skipped entirely and the record is tagged
    `conflict` — callers can surface a diff banner from that state.
    """
    entity = _registry.get(entity_type)
    if entity is None or entity.pull_fn is None:
        return SyncOutcome(
            direction="pull",
            status="failed",
            error=f"no pull handler registered for '{entity_type}'",
        )

    record = await _upsert_record(
        db,
        entity_type=entity_type,
        external_id=external_id,
        business_id=business_id,
        user_id=user_id,
    )
    # Helm-wins gate.
    if record.local_updated_at and external_updated_at < record.local_updated_at:
        record.last_direction = "pull"
        record.last_status = "conflict"
        record.external_updated_at = external_updated_at
        record.payload = {
            **record.payload,
            "last_conflict": {
                "external_ts": external_updated_at.isoformat(),
                "local_ts": record.local_updated_at.isoformat(),
                "event": payload or {},
            },
        }
        await db.commit()
        log.info(
            "sync.pull_conflict",
            entity=entity_type,
            external_id=external_id,
            external_ts=external_updated_at.isoformat(),
            local_ts=record.local_updated_at.isoformat(),
        )
        await _emit_sync_event(
            db,
            business_id=business_id,
            direction="pull",
            status="conflict",
            entity_type=entity_type,
            external_id=external_id,
            detail={
                "reason": "helm_wins",
                "external_ts": external_updated_at.isoformat(),
                "local_ts": record.local_updated_at.isoformat(),
            },
        )
        return SyncOutcome(
            direction="pull",
            status="conflict",
            record_id=record.id,
            detail={"reason": "helm_wins", "external_ts": external_updated_at.isoformat()},
        )

    ctx = PullContext(
        entity_type=entity_type,
        external_id=external_id,
        business_id=business_id,
        user_id=user_id,
        external_updated_at=external_updated_at,
        payload=payload or {},
    )
    try:
        detail = await entity.pull_fn(db, ctx)
        record.last_direction = "pull"
        record.last_status = "ok"
        record.last_error = None
        record.external_updated_at = external_updated_at
        record.payload = {**record.payload, "last_pull": detail}
        await db.commit()
        log.info("sync.pull_ok", entity=entity_type, external_id=external_id)
        await _emit_sync_event(
            db,
            business_id=business_id,
            direction="pull",
            status="ok",
            entity_type=entity_type,
            external_id=external_id,
            detail=detail,
        )
        return SyncOutcome(
            direction="pull",
            status="ok",
            record_id=record.id,
            detail=detail,
        )
    except Exception as e:
        err = str(e)[:500]
        record.last_direction = "pull"
        record.last_status = "failed"
        record.last_error = err
        await db.commit()
        log.warning("sync.pull_failed", entity=entity_type, err=err)
        await _emit_sync_event(
            db,
            business_id=business_id,
            direction="pull",
            status="failed",
            entity_type=entity_type,
            external_id=external_id,
            detail={"error": err},
        )
        return SyncOutcome(
            direction="pull",
            status="failed",
            error=err,
            record_id=record.id,
        )


async def _emit_sync_event(
    db: AsyncSession,
    *,
    business_id: uuid.UUID | None,
    direction: str,
    status: str,
    entity_type: str,
    external_id: str,
    detail: dict[str, Any],
) -> None:
    """Write an `agent_events` row tying the sync outcome to the business's
    most-recent agent session. Surfaces sync activity on the Events page
    alongside tool calls and approvals. Best-effort — a missing session
    just skips the emit so we never kill a sync path on log failure.

    event_type = `sync_{direction}_{status}`:
      sync_push_ok, sync_push_failed, sync_pull_ok, sync_pull_failed,
      sync_pull_conflict.
    """
    if business_id is None:
        return
    sess_q = await db.execute(
        select(AgentSession)
        .where(AgentSession.business_id == business_id)
        .order_by(AgentSession.last_active_at.desc())
        .limit(1)
    )
    sess = sess_q.scalar_one_or_none()
    if sess is None:
        return
    try:
        await event_log.write(
            db,
            session_id=sess.id,
            business_id=business_id,
            event_type=f"sync_{direction}_{status}",
            agent_name="sync_bus",
            payload={
                "entity_type": entity_type,
                "external_id": external_id,
                "detail": detail,
            },
        )
        await db.commit()
    except Exception as e:
        log.warning("sync_bus.emit_failed", err=str(e)[:200])


async def _upsert_record(
    db: AsyncSession,
    *,
    entity_type: str,
    external_id: str,
    business_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
) -> SyncRecord:
    row_q = await db.execute(
        select(SyncRecord).where(
            SyncRecord.entity_type == entity_type,
            SyncRecord.external_id == external_id,
        )
    )
    row = row_q.scalar_one_or_none()
    if row is not None:
        if business_id is not None and row.business_id is None:
            row.business_id = business_id
        if user_id is not None and row.user_id is None:
            row.user_id = user_id
        return row
    row = SyncRecord(
        entity_type=entity_type,
        external_id=external_id,
        business_id=business_id,
        user_id=user_id,
    )
    db.add(row)
    await db.flush()
    return row


# ────────────────────────────────────────────────────────────────
# Lookup — for UI "synced X ago" chips
# ────────────────────────────────────────────────────────────────


async def status_for(
    db: AsyncSession,
    *,
    entity_type: str,
    external_id: str,
) -> SyncRecord | None:
    row_q = await db.execute(
        select(SyncRecord).where(
            SyncRecord.entity_type == entity_type,
            SyncRecord.external_id == external_id,
        )
    )
    return row_q.scalar_one_or_none()


async def statuses_for_business(
    db: AsyncSession, *, business_id: uuid.UUID
) -> list[SyncRecord]:
    row_q = await db.execute(
        select(SyncRecord)
        .where(SyncRecord.business_id == business_id)
        .order_by(SyncRecord.local_updated_at.desc())
    )
    return list(row_q.scalars().all())

"""Agent-session lifecycle.

The CEO Agent has one persistent session per user (cross-business orchestrator).
Sub-agent work uses short-lived child sessions scoped to a specific business —
that lands in Session 2 alongside `delegate_to_specialist`.

For Phase 1 we just ensure exactly one active session per user, created on
first `/chat` hit and reused thereafter. `last_active_at` moves on every turn.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.db.models import AgentSession


async def get_or_create_ceo_session(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> AgentSession:
    """Return the user's CEO Agent session, creating it on first call.

    "CEO" session = `business_id IS NULL` (cross-business). Status='active'.
    """
    result = await db.execute(
        select(AgentSession)
        .where(
            AgentSession.user_id == user_id,
            AgentSession.business_id.is_(None),
            AgentSession.status == "active",
        )
        .order_by(AgentSession.created_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.last_active_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(existing)
        return existing

    row = AgentSession(user_id=user_id, business_id=None, status="active")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row

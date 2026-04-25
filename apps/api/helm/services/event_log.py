"""Event log — the source of truth for every agent action.

CLAUDE.md hard rule #4: "Every agent action is logged. Event-sourced. User
can replay any decision." Every tool call, user message, agent response, and
approval touches this module. Writes are synchronous inside the tool wrapper
so a crash before logging never "loses" a decision.

Schema is in `helm.db.models.AgentEvent`; we never bypass it to insert raw rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.db.models import AgentEvent


@dataclass(frozen=True, slots=True)
class LoggedEvent:
    id: int
    session_id: uuid.UUID
    business_id: uuid.UUID | None
    event_type: str
    agent_name: str


async def write(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    event_type: str,
    agent_name: str,
    payload: dict[str, Any],
    business_id: uuid.UUID | None = None,
    cost_cents: int = 0,
) -> LoggedEvent:
    """Insert a single agent event. Commits before returning.

    `event_type` values in use:
      - 'message.user'     — a user message into the chat
      - 'message.agent'    — an agent response (streaming complete)
      - 'tool_call'        — agent invoked a tool
      - 'tool_result'      — tool returned a result
      - 'approval_requested' / 'approval_approved' / 'approval_denied'
        / 'approval_modified'
      - 'spend_intent' / 'spend_authorized' / 'spend_declined'
      - 'kill_switch_activated'
      - 'specialist_completed'
      - 'computer_use_requested'
      - 'error'
    """
    row = AgentEvent(
        session_id=session_id,
        business_id=business_id,
        event_type=event_type,
        agent_name=agent_name,
        payload=payload,
        cost_cents=cost_cents,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return LoggedEvent(
        id=row.id,
        session_id=row.session_id,
        business_id=row.business_id,
        event_type=row.event_type,
        agent_name=row.agent_name,
    )


async def recent_for_session(
    session: AsyncSession,
    session_id: uuid.UUID,
    limit: int = 50,
) -> list[AgentEvent]:
    """Latest events for a session, newest-first. For the `query_event_log` tool
    the CEO Agent exposes to the user's 'Why did you do that?' affordance."""
    result = await session.execute(
        select(AgentEvent)
        .where(AgentEvent.session_id == session_id)
        .order_by(AgentEvent.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())

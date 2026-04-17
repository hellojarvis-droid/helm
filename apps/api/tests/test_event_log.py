"""Event log — write + read-back."""

from __future__ import annotations

import pytest
from helm.db.models import AgentSession, User
from helm.services import event_log

from tests.conftest import requires_db


@requires_db
@pytest.mark.asyncio
async def test_write_and_recent_roundtrip(session) -> None:
    user = User(supabase_id="sub-e1", email="e1@example.com", tier="founder")
    session.add(user)
    await session.flush()

    ag = AgentSession(user_id=user.id, business_id=None, status="active")
    session.add(ag)
    await session.commit()

    logged = await event_log.write(
        session,
        session_id=ag.id,
        event_type="message.user",
        agent_name="user",
        payload={"text": "hello"},
    )
    assert logged.id > 0
    assert logged.session_id == ag.id
    assert logged.event_type == "message.user"

    await event_log.write(
        session,
        session_id=ag.id,
        event_type="message.agent",
        agent_name="ceo_agent",
        payload={"text": "hi there"},
        cost_cents=3,
    )

    events = await event_log.recent_for_session(session, ag.id, limit=10)
    assert len(events) == 2
    assert events[0].event_type == "message.agent"  # newest-first
    assert events[1].event_type == "message.user"
    assert events[0].cost_cents == 3

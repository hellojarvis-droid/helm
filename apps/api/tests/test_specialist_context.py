"""BusinessContext enrichment — brand_kit + integrations + recent events."""

from __future__ import annotations

import pytest
from helm.agents.specialists.base import _hydrate_context
from helm.db.models import AgentSession, Business, Integration, User
from helm.services import event_log

from tests.conftest import requires_db


@requires_db
@pytest.mark.asyncio
async def test_hydrate_loads_kit_integrations_and_events(session) -> None:
    user = User(supabase_id="sub-ctx-1", email="ctx@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Ember",
        vertical="dtc_physical",
        brand_kit={"name": "Ember", "tagline": "slow fires"},
    )
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=None, status="active")
    session.add(ag)
    await session.flush()
    active_integ = Integration(
        business_id=biz.id,
        toolkit="gmail",
        composio_connection_id="conn_active",
        status="active",
        meta={},
    )
    pending_integ = Integration(
        business_id=biz.id,
        toolkit="shopify",
        composio_connection_id="conn_pending",
        status="pending",
        meta={},
    )
    session.add_all([active_integ, pending_integ])
    await session.commit()

    # Seed a couple of events so recent_events has content.
    await event_log.write(
        session,
        session_id=ag.id,
        event_type="message.user",
        agent_name="user",
        payload={"text": "brand my candle biz"},
    )
    await event_log.write(
        session,
        session_id=ag.id,
        event_type="message.agent",
        agent_name="ceo_agent",
        payload={"text": "Working on it."},
    )

    ctx = await _hydrate_context(session, user.id, biz.id, ag.id)

    assert ctx.business_name == "Ember"
    assert ctx.vertical == "dtc_physical"
    assert ctx.brand_kit["name"] == "Ember"
    assert ctx.brand_kit["tagline"] == "slow fires"
    # Only the active toolkit — pending excluded.
    assert set(ctx.connected_integrations) == {"gmail"}
    # Newest-first, at least the two we wrote.
    assert len(ctx.recent_events) >= 2
    assert ctx.recent_events[0]["event_type"] in {"message.user", "message.agent"}


@requires_db
@pytest.mark.asyncio
async def test_hydrate_without_business_returns_empty_kit(session) -> None:
    user = User(supabase_id="sub-ctx-2", email="ctx2@example.com", tier="founder")
    session.add(user)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=None, status="active")
    session.add(ag)
    await session.commit()

    ctx = await _hydrate_context(session, user.id, None, ag.id)
    assert ctx.business_id is None
    assert ctx.business_name == ""
    assert ctx.brand_kit == {}
    assert ctx.connected_integrations == ()

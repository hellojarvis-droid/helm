"""GET /businesses/{id}/events — read-back with tenant isolation + pagination."""

from __future__ import annotations

import pytest
from helm.auth import CurrentUser, require_user
from helm.db.models import AgentSession, Business, User
from helm.main import create_app
from helm.services import event_log
from httpx import ASGITransport, AsyncClient

from tests.conftest import requires_db


@requires_db
@pytest.mark.asyncio
async def test_list_events_for_business(session) -> None:
    user = User(supabase_id="sub-ev-1", email="ev1@example.com", tier="founder")
    session.add(user)
    await session.flush()

    biz = Business(user_id=user.id, name="Candle Co", vertical="dtc_physical", status="active")
    session.add(biz)
    await session.flush()

    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.commit()

    for i in range(5):
        await event_log.write(
            session,
            session_id=ag.id,
            business_id=biz.id,
            event_type="tool_call",
            agent_name="ceo_agent",
            payload={"i": i},
        )

    fake = CurrentUser(supabase_id="sub-ev-1", email="ev1@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            f"/businesses/{biz.id}/events",
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 5
        # Newest-first by id DESC.
        ids = [row["id"] for row in rows]
        assert ids == sorted(ids, reverse=True)
        assert all(row["event_type"] == "tool_call" for row in rows)

        # Cursor pagination via before_id.
        r = await client.get(
            f"/businesses/{biz.id}/events",
            params={"limit": 2, "before_id": ids[0]},
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 200
        page = r.json()
        assert len(page) == 2
        assert page[0]["id"] < ids[0]


@requires_db
@pytest.mark.asyncio
async def test_events_tenant_isolation(session) -> None:
    user_a = User(supabase_id="sub-ev-a", email="a@example.com", tier="founder")
    user_b = User(supabase_id="sub-ev-b", email="b@example.com", tier="founder")
    session.add_all([user_a, user_b])
    await session.flush()

    biz_a = Business(user_id=user_a.id, name="A", vertical="dtc_physical", status="active")
    session.add(biz_a)
    await session.flush()

    ag = AgentSession(user_id=user_a.id, business_id=biz_a.id, status="active")
    session.add(ag)
    await session.commit()

    await event_log.write(
        session,
        session_id=ag.id,
        business_id=biz_a.id,
        event_type="tool_call",
        agent_name="ceo_agent",
        payload={},
    )

    # B tries to read A's events — must 404 (fail-closed, same rule as GET /businesses/{id}).
    fake_b = CurrentUser(supabase_id="sub-ev-b", email="b@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_b
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            f"/businesses/{biz_a.id}/events",
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 404

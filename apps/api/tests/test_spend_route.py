"""GET /businesses/{id}/spend — aggregate over recent agent events."""

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
async def test_spend_summary(session) -> None:
    user = User(supabase_id="sub-sp-1", email="sp@example.com", tier="founder")
    session.add(user)
    await session.flush()

    biz = Business(
        user_id=user.id,
        name="Candle Co",
        vertical="dtc_physical",
        status="active",
        weekly_spend_cap_cents=50_000,  # $500
    )
    session.add(biz)
    await session.flush()

    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.commit()

    # Three approved spends: $25 + $50 + $17 = $92
    for amount in (2500, 5000, 1700):
        await event_log.write(
            session,
            session_id=ag.id,
            business_id=biz.id,
            event_type="spend_authorized",
            agent_name="stripe_authorization",
            payload={"amount_cents": amount},
            cost_cents=amount,
        )
    # One declined
    await event_log.write(
        session,
        session_id=ag.id,
        business_id=biz.id,
        event_type="spend_declined",
        agent_name="stripe_authorization",
        payload={"reason": "mcc_not_allowed:5812"},
    )
    # Two LLM turns: 3¢ + 4¢
    for llm_cost in (3, 4):
        await event_log.write(
            session,
            session_id=ag.id,
            business_id=biz.id,
            event_type="message.agent",
            agent_name="ceo_agent",
            payload={"text": "…"},
            cost_cents=llm_cost,
        )

    fake = CurrentUser(supabase_id="sub-sp-1", email="sp@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            f"/businesses/{biz.id}/spend",
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["weekly_cap_cents"] == 50_000
        assert body["week_to_date_cents"] == 9_200
        assert body["remaining_cents"] == 40_800
        assert body["llm_cost_cents"] == 7
        assert body["declined_count"] == 1
        assert body["window_days"] == 7


@requires_db
@pytest.mark.asyncio
async def test_spend_tenant_isolation(session) -> None:
    user_a = User(supabase_id="sub-sp-a", email="a@example.com", tier="founder")
    user_b = User(supabase_id="sub-sp-b", email="b@example.com", tier="founder")
    session.add_all([user_a, user_b])
    await session.flush()

    biz_a = Business(user_id=user_a.id, name="A", vertical="dtc_physical", status="active")
    session.add(biz_a)
    await session.commit()

    fake_b = CurrentUser(supabase_id="sub-sp-b", email="b@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_b
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            f"/businesses/{biz_a.id}/spend",
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 404

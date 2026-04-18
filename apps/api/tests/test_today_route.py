"""GET /users/me/today — cross-business aggregate for the landing view."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from helm.auth import CurrentUser, require_user
from helm.db.models import AgentSession, Approval, Business, User
from helm.main import create_app
from helm.services import event_log
from httpx import ASGITransport, AsyncClient

from tests.conftest import requires_db


@requires_db
@pytest.mark.asyncio
async def test_today_aggregates_across_businesses(session) -> None:
    user = User(supabase_id="sub-today", email="today@example.com", tier="founder")
    session.add(user)
    await session.flush()

    biz_a = Business(user_id=user.id, name="Candles", vertical="dtc_physical", status="active")
    biz_b = Business(user_id=user.id, name="SaaS", vertical="saas", status="active")
    session.add_all([biz_a, biz_b])
    await session.flush()

    ag_a = AgentSession(user_id=user.id, business_id=biz_a.id, status="active")
    ag_b = AgentSession(user_id=user.id, business_id=biz_b.id, status="active")
    session.add_all([ag_a, ag_b])
    await session.commit()

    # Biz A: $100 revenue, $40 spend, 1 pending approval.
    await event_log.write(
        session,
        session_id=ag_a.id,
        business_id=biz_a.id,
        event_type="revenue_received",
        agent_name="stripe",
        payload={},
        cost_cents=-10_000,
    )
    await event_log.write(
        session,
        session_id=ag_a.id,
        business_id=biz_a.id,
        event_type="spend_authorized",
        agent_name="stripe_authorization",
        payload={},
        cost_cents=4_000,
    )
    session.add(
        Approval(
            business_id=biz_a.id,
            kind="spend",
            summary="$80 to Meta Ads",
            details={},
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
    )
    # Biz B: $50 revenue, no spend, no pending approvals.
    await event_log.write(
        session,
        session_id=ag_b.id,
        business_id=biz_b.id,
        event_type="revenue_received",
        agent_name="stripe",
        payload={},
        cost_cents=-5_000,
    )
    await session.commit()

    fake = CurrentUser(supabase_id="sub-today", email="today@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/users/me/today", headers={"Authorization": "Bearer stub"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["revenue_today_cents"] == 15_000
        assert body["spend_today_cents"] == 4_000
        assert body["net_today_cents"] == 11_000
        assert body["pending_approval_count"] == 1
        assert body["window_hours"] == 24
        assert len(body["businesses"]) == 2

        rows = {b["name"]: b for b in body["businesses"]}
        assert rows["Candles"]["revenue_today_cents"] == 10_000
        assert rows["Candles"]["spend_today_cents"] == 4_000
        assert rows["Candles"]["net_today_cents"] == 6_000
        assert rows["Candles"]["pending_approval_count"] == 1
        assert rows["SaaS"]["revenue_today_cents"] == 5_000
        assert rows["SaaS"]["spend_today_cents"] == 0
        assert rows["SaaS"]["pending_approval_count"] == 0


@requires_db
@pytest.mark.asyncio
async def test_today_tenant_isolation(session) -> None:
    user_a = User(supabase_id="sub-t-a", email="ta@example.com", tier="founder")
    user_b = User(supabase_id="sub-t-b", email="tb@example.com", tier="founder")
    session.add_all([user_a, user_b])
    await session.flush()
    biz_a = Business(user_id=user_a.id, name="A", vertical="dtc_physical", status="active")
    session.add(biz_a)
    await session.flush()
    ag_a = AgentSession(user_id=user_a.id, business_id=biz_a.id, status="active")
    session.add(ag_a)
    await session.commit()
    await event_log.write(
        session,
        session_id=ag_a.id,
        business_id=biz_a.id,
        event_type="revenue_received",
        agent_name="stripe",
        payload={},
        cost_cents=-9_000,
    )
    await session.commit()

    fake_b = CurrentUser(supabase_id="sub-t-b", email="tb@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_b
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/users/me/today", headers={"Authorization": "Bearer stub"})
        assert r.status_code == 200
        body = r.json()
        # B sees no revenue — A's numbers must not leak.
        assert body["revenue_today_cents"] == 0
        assert body["businesses"] == []

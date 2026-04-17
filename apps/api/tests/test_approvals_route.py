"""Approvals REST — list / get / respond, with the event-log handoff."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from helm.auth import CurrentUser, require_user
from helm.db.models import AgentEvent, AgentSession, Approval, Business, User
from helm.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.conftest import requires_db


async def _seed_user_with_pending_approval(session) -> tuple[User, Business, Approval]:
    user = User(supabase_id="sub-appr", email="appr@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="Candle", vertical="dtc_physical")
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=None, status="active")
    session.add(ag)
    await session.flush()
    approval = Approval(
        business_id=biz.id,
        kind="spend",
        summary="Spend $340 on 3 TikTok creatives.",
        details={},
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    session.add(approval)
    await session.commit()
    return user, biz, approval


@requires_db
@pytest.mark.asyncio
async def test_approval_approve_writes_event(session) -> None:
    user, biz, approval = await _seed_user_with_pending_approval(session)

    fake_user = CurrentUser(supabase_id=user.supabase_id, email=user.email, raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/approvals/{approval.id}/respond",
            json={"status": "approved"},
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "approved"
        assert body["responded_at"] is not None

        # Listing returns the resolved approval.
        r = await client.get("/approvals", headers={"Authorization": "Bearer stub"})
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["status"] == "approved"

    # Event-log handoff: an approval_approved event should exist on user's session.
    rows = (
        (
            await session.execute(
                select(AgentEvent)
                .where(AgentEvent.event_type == "approval_approved")
                .where(AgentEvent.business_id == biz.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].agent_name == "user"
    assert rows[0].payload["approval_id"] == str(approval.id)


@requires_db
@pytest.mark.asyncio
async def test_approval_denied_locks_out_retry(session) -> None:
    user, _, approval = await _seed_user_with_pending_approval(session)

    fake_user = CurrentUser(supabase_id=user.supabase_id, email=user.email, raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/approvals/{approval.id}/respond",
            json={"status": "denied"},
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 200

        # Second respond on a terminal approval must 409.
        r = await client.post(
            f"/approvals/{approval.id}/respond",
            json={"status": "approved"},
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 409


@requires_db
@pytest.mark.asyncio
async def test_approval_cross_tenant_isolation(session) -> None:
    _, _, approval_a = await _seed_user_with_pending_approval(session)

    # User B can't touch A's approval.
    user_b = User(supabase_id="sub-appr-b", email="b@example.com", tier="founder")
    session.add(user_b)
    await session.commit()

    fake_b = CurrentUser(supabase_id=user_b.supabase_id, email=user_b.email, raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_b
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            f"/approvals/{approval_a.id}",
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 404
        r = await client.post(
            f"/approvals/{approval_a.id}/respond",
            json={"status": "approved"},
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 404

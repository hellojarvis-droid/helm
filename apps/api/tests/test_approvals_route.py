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
async def test_approval_modified_raises_weekly_cap(session) -> None:
    """Tapping "Approve & raise cap" on a spend approval bumps the business's
    weekly_spend_cap_cents atomically with the approval response.
    """
    user = User(supabase_id="sub-raise", email="raise@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle Co",
        vertical="dtc_physical",
        weekly_spend_cap_cents=10_000,  # $100 cap
    )
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.flush()
    # $60 already spent week-to-date.
    from helm.services import event_log

    await event_log.write(
        session,
        session_id=ag.id,
        business_id=biz.id,
        event_type="spend_authorized",
        agent_name="stripe_authorization",
        payload={},
        cost_cents=6_000,
    )
    # Pending approval: $80 (would push to $140, above $100 cap).
    approval = Approval(
        business_id=biz.id,
        kind="spend",
        summary="Spend $80 on Meta Ads creative test.",
        details={"amount_cents": 8_000, "merchant_hint": "Meta"},
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    session.add(approval)
    await session.commit()

    fake_user = CurrentUser(supabase_id=user.supabase_id, email=user.email, raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/approvals/{approval.id}/respond",
            json={"status": "modified", "modifications": {"raise_weekly_cap": True}},
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "modified"
        # cap_raise should be on the response body so the client can render
        # "cap raised to $N" without a second fetch.
        assert body["cap_raise"]["changed"] is True
        assert body["cap_raise"]["old_cap_cents"] == 10_000
        assert body["cap_raise"]["new_cap_cents"] == 24_000

    # Business cap should now be wtd ($60) + amount ($80) + buffer ($100) = $240.
    await session.refresh(biz)
    assert biz.weekly_spend_cap_cents == 24_000

    # The approval's details should carry the user modification record.
    await session.refresh(approval)
    assert approval.details["user_modifications"]["raise_weekly_cap"] is True

    # The event-log event should carry a cap_raise block for audit.
    rows = (
        (
            await session.execute(
                select(AgentEvent)
                .where(AgentEvent.event_type == "approval_modified")
                .where(AgentEvent.business_id == biz.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    meta = rows[0].payload["cap_raise"]
    assert meta["changed"] is True
    assert meta["old_cap_cents"] == 10_000
    assert meta["new_cap_cents"] == 24_000


@requires_db
@pytest.mark.asyncio
async def test_cap_raise_syncs_to_stripe_when_card_exists(session, monkeypatch) -> None:
    """When the business has an Issuing card and the user raises the cap,
    the new limit is pushed to Stripe so the card's own spending_controls
    stay in sync with our DB cap.
    """
    from helm import config
    from helm.services import event_log
    from helm.services import stripe_client as stripe_module

    user = User(supabase_id="sub-sync", email="sync@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle Co",
        vertical="dtc_physical",
        weekly_spend_cap_cents=10_000,  # $100
        stripe_account_id="acct_test",
        stripe_card_id="ic_test",
    )
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.flush()
    approval = Approval(
        business_id=biz.id,
        kind="spend",
        summary="Spend $80 on Meta Ads.",
        details={"amount_cents": 8_000, "merchant_hint": "Meta"},
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    session.add(approval)
    await session.commit()
    # A prior $60 authorized so wtd math matches the non-stripe test.
    await event_log.write(
        session,
        session_id=ag.id,
        business_id=biz.id,
        event_type="spend_authorized",
        agent_name="stripe_authorization",
        payload={},
        cost_cents=6_000,
    )
    await session.commit()

    # Enable Issuing for this test, and stub the Stripe SDK call.
    calls: list[dict[str, object]] = []

    async def _fake_update(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(stripe_module, "update_issuing_weekly_cap", _fake_update)

    # Flip the settings flag. get_settings is cached via lru_cache; clear it.
    monkeypatch.setenv("STRIPE_ISSUING_ENABLED", "true")
    config.get_settings.cache_clear()

    fake_user = CurrentUser(supabase_id=user.supabase_id, email=user.email, raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/approvals/{approval.id}/respond",
            json={"status": "modified", "modifications": {"raise_weekly_cap": True}},
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 200, r.text
        body = r.json()

    cap_raise = body["cap_raise"]
    assert cap_raise["changed"] is True
    assert cap_raise["new_cap_cents"] == 24_000  # wtd $60 + amt $80 + $100 buf
    assert cap_raise["stripe_sync"]["attempted"] is True
    assert cap_raise["stripe_sync"]["synced"] is True

    assert len(calls) == 1
    assert calls[0]["account_id"] == "acct_test"
    assert calls[0]["card_id"] == "ic_test"
    assert calls[0]["weekly_spend_cap_cents"] == 24_000

    config.get_settings.cache_clear()


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

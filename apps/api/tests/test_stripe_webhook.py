"""Stripe webhook — signature + dispatch + account-update side effects.

Signature verification is mocked by patching `stripe_client.verify_webhook`
so we don't need a real Stripe secret + signed payload. Actual integration
with Stripe's signing lives in stripe_client.verify_webhook (unit-tested
by Stripe's own SDK); our coverage is the glue.
"""

from __future__ import annotations

import json

import pytest
import stripe
from helm.db.models import Business, User
from helm.main import create_app
from helm.services import stripe_client
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.conftest import requires_db


def _mk_event(event_type: str, obj: dict) -> dict:
    return {"type": event_type, "data": {"object": obj}}


@pytest.mark.asyncio
async def test_webhook_rejects_bad_signature(monkeypatch) -> None:
    def _raise(*a, **k):
        raise stripe.SignatureVerificationError("nope", "sig-header", "body")

    monkeypatch.setattr(stripe_client, "verify_webhook", _raise)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=deadbeef"},
        )
    assert r.status_code == 401


@requires_db
@pytest.mark.asyncio
async def test_account_updated_flips_onboarding_complete(session, monkeypatch) -> None:
    user = User(supabase_id="sub-sw-1", email="sw1@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle",
        vertical="dtc_physical",
        stripe_account_id="acct_onboard",
    )
    session.add(biz)
    await session.commit()

    event = _mk_event(
        "account.updated",
        {
            "id": "acct_onboard",
            "details_submitted": True,
            "charges_enabled": True,
            "payouts_enabled": True,
            "requirements": {"currently_due": []},
        },
    )
    monkeypatch.setattr(stripe_client, "verify_webhook", lambda body, sig: event)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/stripe",
            content=json.dumps(event).encode(),
            headers={"stripe-signature": "t=1,v1=ok"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"
    assert r.json()["onboarding_complete"] is True

    # DB flipped (fresh session to bypass ORM cache).
    from helm.db.session import get_sessionmaker

    sm = get_sessionmaker()
    async with sm() as s2:
        refreshed = (await s2.execute(select(Business).where(Business.id == biz.id))).scalar_one()
        assert refreshed.stripe_onboarding_complete is True


@requires_db
@pytest.mark.asyncio
async def test_payment_succeeded_logs_revenue_event(session, monkeypatch) -> None:
    """payment_intent.succeeded on a connected account writes a
    `revenue_received` event linked to the business, with cost_cents as
    negative inflow so /spend can sum + flip sign without schema changes.
    """
    from helm.db.models import AgentEvent, AgentSession

    user = User(supabase_id="sub-rev", email="rev@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle",
        vertical="dtc_physical",
        stripe_account_id="acct_rev",
    )
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.commit()

    event = _mk_event(
        "payment_intent.succeeded",
        {
            "id": "pi_test_1",
            "stripe_account": "acct_rev",
            "amount_received": 12_500,
            "currency": "usd",
        },
    )
    monkeypatch.setattr(stripe_client, "verify_webhook", lambda body, sig: event)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/stripe",
            content=json.dumps(event).encode(),
            headers={"stripe-signature": "t=1,v1=ok"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["amount_cents"] == 12_500

    from helm.db.session import get_sessionmaker

    sm = get_sessionmaker()
    async with sm() as s2:
        rows = (
            (
                await s2.execute(
                    select(AgentEvent).where(
                        AgentEvent.business_id == biz.id,
                        AgentEvent.event_type == "revenue_received",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].cost_cents == -12_500  # negative = inflow
        assert rows[0].payload["intent_id"] == "pi_test_1"


@requires_db
@pytest.mark.asyncio
async def test_account_updated_keeps_incomplete_when_requirements_due(session, monkeypatch) -> None:
    user = User(supabase_id="sub-sw-2", email="sw2@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle",
        vertical="dtc_physical",
        stripe_account_id="acct_partial",
    )
    session.add(biz)
    await session.commit()

    event = _mk_event(
        "account.updated",
        {
            "id": "acct_partial",
            "details_submitted": True,
            "requirements": {"currently_due": ["tos_acceptance"]},
        },
    )
    monkeypatch.setattr(stripe_client, "verify_webhook", lambda body, sig: event)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=ok"},
        )
    assert r.status_code == 200
    assert r.json()["onboarding_complete"] is False


@requires_db
@pytest.mark.asyncio
async def test_issuing_authorization_approved_within_caps(session, monkeypatch) -> None:
    user = User(supabase_id="sub-sw-3", email="sw3@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle",
        vertical="dtc_physical",
        stripe_account_id="acct_cap",
        weekly_spend_cap_cents=50000,  # $500
    )
    session.add(biz)
    await session.commit()

    # Small auth for an allowed MCC category (7372 = Data Processing / SaaS).
    event = _mk_event(
        "issuing_authorization.request",
        {
            "stripe_account": "acct_cap",
            "pending_request": {"amount": 2000},
            "merchant_data": {"category": "7372", "name": "Vercel Inc"},
        },
    )
    monkeypatch.setattr(stripe_client, "verify_webhook", lambda body, sig: event)

    # Seed an AgentSession so the decision event can be written.
    from helm.db.models import AgentSession

    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=ok"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["approved"] is True
    assert r.json()["reason"] == "approved"


@requires_db
@pytest.mark.asyncio
async def test_issuing_authorization_declined_on_kill_switch(session, monkeypatch) -> None:
    from helm.services import kill_switch

    user = User(
        supabase_id="sub-sw-4",
        email="sw4@example.com",
        tier="founder",
        kill_switch_active=True,
    )
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle",
        vertical="dtc_physical",
        stripe_account_id="acct_killed",
    )
    session.add(biz)
    await session.commit()
    kill_switch._invalidate_cache_for_tests()

    event = _mk_event(
        "issuing_authorization.request",
        {
            "stripe_account": "acct_killed",
            "pending_request": {"amount": 1000},
            "merchant_data": {"category": "7372"},
        },
    )
    monkeypatch.setattr(stripe_client, "verify_webhook", lambda body, sig: event)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=ok"},
        )
    assert r.status_code == 200
    assert r.json()["approved"] is False
    assert r.json()["reason"] == "kill_switch_on"


@requires_db
@pytest.mark.asyncio
async def test_issuing_authorization_declined_on_disallowed_mcc(session, monkeypatch) -> None:
    user = User(supabase_id="sub-sw-5", email="sw5@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle",
        vertical="dtc_physical",
        stripe_account_id="acct_mcc",
    )
    session.add(biz)
    await session.commit()

    # 5812 = Eating Places — not on the agent allowlist.
    event = _mk_event(
        "issuing_authorization.request",
        {
            "stripe_account": "acct_mcc",
            "pending_request": {"amount": 1500},
            "merchant_data": {"category": "5812", "name": "Lunch Spot"},
        },
    )
    monkeypatch.setattr(stripe_client, "verify_webhook", lambda body, sig: event)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=ok"},
        )
    assert r.status_code == 200
    assert r.json()["approved"] is False
    assert "mcc_not_allowed" in r.json()["reason"]


@requires_db
@pytest.mark.asyncio
async def test_issuing_authorization_declined_over_weekly_cap(session, monkeypatch) -> None:
    """Seed a recent spend that fills most of the cap; new auth would exceed."""
    from datetime import UTC, datetime

    from helm.db.models import AgentEvent, AgentSession

    user = User(supabase_id="sub-sw-6", email="sw6@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle",
        vertical="dtc_physical",
        stripe_account_id="acct_wcap",
        weekly_spend_cap_cents=10000,  # $100 cap, tight
    )
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.flush()
    # Prior spend this week: $80.
    prior = AgentEvent(
        session_id=ag.id,
        business_id=biz.id,
        event_type="spend_authorized",
        agent_name="stripe_authorization",
        payload={"amount_cents": 8000},
        cost_cents=8000,
        created_at=datetime.now(UTC),
    )
    session.add(prior)
    await session.commit()

    # Attempted $30 — would push us over $100.
    event = _mk_event(
        "issuing_authorization.request",
        {
            "stripe_account": "acct_wcap",
            "pending_request": {"amount": 3000},
            "merchant_data": {"category": "7372"},
        },
    )
    monkeypatch.setattr(stripe_client, "verify_webhook", lambda body, sig: event)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=ok"},
        )
    assert r.status_code == 200
    assert r.json()["approved"] is False
    assert "weekly_cap_would_exceed" in r.json()["reason"]


@requires_db
@pytest.mark.asyncio
async def test_unknown_event_type_ignored(monkeypatch) -> None:
    event = _mk_event("customer.created", {"id": "cus_x"})
    monkeypatch.setattr(stripe_client, "verify_webhook", lambda body, sig: event)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=ok"},
        )
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


def test_auth_default_mcc_allowlist_includes_expected_categories() -> None:
    """Quick sanity — agent-relevant MCCs are on the list; food is not."""
    from helm.services.stripe_authorization import _DEFAULT_MCC_ALLOWLIST

    assert "7372" in _DEFAULT_MCC_ALLOWLIST  # SaaS / data processing
    assert "7311" in _DEFAULT_MCC_ALLOWLIST  # Advertising
    assert "5999" in _DEFAULT_MCC_ALLOWLIST  # Misc retail (POD)
    assert "5812" not in _DEFAULT_MCC_ALLOWLIST  # Eating places
    assert "5921" not in _DEFAULT_MCC_ALLOWLIST  # Package Stores — Beer

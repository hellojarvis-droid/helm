"""Webhook calls Stripe to ENFORCE the authorization decision."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from helm.db.models import AgentSession, Business, User
from helm.main import create_app
from helm.services import stripe_client
from httpx import ASGITransport, AsyncClient

from tests.conftest import requires_db


def _mk_event(event_type: str, obj: dict) -> dict:
    return {"type": event_type, "data": {"object": obj}}


@requires_db
@pytest.mark.asyncio
async def test_webhook_approves_at_stripe_on_approve(session, monkeypatch) -> None:
    user = User(supabase_id="sub-en-1", email="en1@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle",
        vertical="dtc_physical",
        stripe_account_id="acct_en",
        weekly_spend_cap_cents=50000,
    )
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.commit()

    event = _mk_event(
        "issuing_authorization.request",
        {
            "id": "iauth_abc",
            "stripe_account": "acct_en",
            "pending_request": {"amount": 1000},
            "merchant_data": {"category": "7372", "name": "Vercel"},
        },
    )
    monkeypatch.setattr(stripe_client, "verify_webhook", lambda body, sig: event)
    approve_mock = AsyncMock()
    decline_mock = AsyncMock()
    monkeypatch.setattr(stripe_client, "approve_authorization", approve_mock)
    monkeypatch.setattr(stripe_client, "decline_authorization", decline_mock)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/stripe",
            content=json.dumps(event).encode(),
            headers={"stripe-signature": "t=1,v1=ok"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["approved"] is True

    approve_mock.assert_awaited_once_with("iauth_abc", "acct_en")
    decline_mock.assert_not_awaited()


@requires_db
@pytest.mark.asyncio
async def test_webhook_declines_at_stripe_on_deny(session, monkeypatch) -> None:
    user = User(supabase_id="sub-en-2", email="en2@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle",
        vertical="dtc_physical",
        stripe_account_id="acct_en2",
    )
    session.add(biz)
    await session.commit()

    # MCC 5812 (Eating Places) is NOT on the allowlist → deny.
    event = _mk_event(
        "issuing_authorization.request",
        {
            "id": "iauth_xyz",
            "stripe_account": "acct_en2",
            "pending_request": {"amount": 1500},
            "merchant_data": {"category": "5812", "name": "Lunch Spot"},
        },
    )
    monkeypatch.setattr(stripe_client, "verify_webhook", lambda body, sig: event)
    approve_mock = AsyncMock()
    decline_mock = AsyncMock()
    monkeypatch.setattr(stripe_client, "approve_authorization", approve_mock)
    monkeypatch.setattr(stripe_client, "decline_authorization", decline_mock)

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
    decline_mock.assert_awaited_once()
    call = decline_mock.call_args
    assert call.args[0] == "iauth_xyz"
    assert call.args[1] == "acct_en2"
    # Reason passed so it shows in Stripe's dashboard for audit.
    assert "mcc_not_allowed" in call.kwargs["reason"]
    approve_mock.assert_not_awaited()


@requires_db
@pytest.mark.asyncio
async def test_webhook_returns_200_even_if_stripe_enforce_fails(session, monkeypatch) -> None:
    """Enforcement failure must not propagate as 5xx — Stripe would retry
    relentlessly. We still return 200 with the decision + enforcement_error."""
    user = User(supabase_id="sub-en-3", email="en3@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle",
        vertical="dtc_physical",
        stripe_account_id="acct_en3",
    )
    session.add(biz)
    await session.commit()

    event = _mk_event(
        "issuing_authorization.request",
        {
            "id": "iauth_fail",
            "stripe_account": "acct_en3",
            "pending_request": {"amount": 1000},
            "merchant_data": {"category": "7372"},
        },
    )
    monkeypatch.setattr(stripe_client, "verify_webhook", lambda body, sig: event)
    monkeypatch.setattr(
        stripe_client,
        "approve_authorization",
        AsyncMock(side_effect=RuntimeError("stripe API blew up")),
    )
    monkeypatch.setattr(stripe_client, "decline_authorization", AsyncMock())

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/stripe",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=ok"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["approved"] is True
    assert "stripe API blew up" in body["enforcement_error"]

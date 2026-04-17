"""Stripe Connect onboarding — creation + idempotency + tenant isolation.

Stripe SDK is fully mocked; no real API calls. We verify our glue writes the
right DB state and proxies the onboarding URL back.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from helm.auth import CurrentUser, require_user
from helm.db.models import Business, User
from helm.main import create_app
from helm.services import stripe_client
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.conftest import requires_db


def _fake_link(account_id: str) -> stripe_client.OnboardingLink:
    return stripe_client.OnboardingLink(
        account_id=account_id,
        onboarding_url=f"https://connect.stripe.com/setup/c/{account_id}",
        expires_at=1_800_000_000,
    )


@requires_db
@pytest.mark.asyncio
async def test_onboard_creates_account_and_returns_link(session, monkeypatch) -> None:
    user = User(supabase_id="sub-so-1", email="so1@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="Candle", vertical="dtc_physical")
    session.add(biz)
    await session.commit()

    monkeypatch.setattr(
        stripe_client, "create_connect_account", AsyncMock(return_value="acct_test123")
    )
    monkeypatch.setattr(
        stripe_client, "create_account_link", AsyncMock(return_value=_fake_link("acct_test123"))
    )

    fake_user = CurrentUser(supabase_id=user.supabase_id, email=user.email, raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/businesses/{biz.id}/stripe/onboard",
            headers={"Authorization": "Bearer stub"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account_id"] == "acct_test123"
    assert body["onboarding_url"].startswith("https://")
    assert body["reused_existing_account"] is False

    # DB: business has the account id.
    from helm.db.session import get_sessionmaker

    sm = get_sessionmaker()
    async with sm() as s2:
        refreshed = (await s2.execute(select(Business).where(Business.id == biz.id))).scalar_one()
        assert refreshed.stripe_account_id == "acct_test123"


@requires_db
@pytest.mark.asyncio
async def test_onboard_is_idempotent_reuses_existing_account(session, monkeypatch) -> None:
    user = User(supabase_id="sub-so-2", email="so2@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle",
        vertical="dtc_physical",
        stripe_account_id="acct_already",
    )
    session.add(biz)
    await session.commit()

    create_mock = AsyncMock(return_value="acct_SHOULD_NOT_BE_CALLED")
    monkeypatch.setattr(stripe_client, "create_connect_account", create_mock)
    monkeypatch.setattr(
        stripe_client, "create_account_link", AsyncMock(return_value=_fake_link("acct_already"))
    )

    fake_user = CurrentUser(supabase_id=user.supabase_id, email=user.email, raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/businesses/{biz.id}/stripe/onboard",
            headers={"Authorization": "Bearer stub"},
        )
    assert r.status_code == 200
    assert r.json()["account_id"] == "acct_already"
    assert r.json()["reused_existing_account"] is True
    create_mock.assert_not_called()


@requires_db
@pytest.mark.asyncio
async def test_onboard_cross_tenant_404(session, monkeypatch) -> None:
    user_a = User(supabase_id="sub-so-a", email="a@example.com", tier="founder")
    user_b = User(supabase_id="sub-so-b", email="b@example.com", tier="founder")
    session.add_all([user_a, user_b])
    await session.flush()
    biz = Business(user_id=user_a.id, name="A's", vertical="dtc_physical")
    session.add(biz)
    await session.commit()

    fake_b = CurrentUser(supabase_id=user_b.supabase_id, email=user_b.email, raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_b
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/businesses/{biz.id}/stripe/onboard",
            headers={"Authorization": "Bearer stub"},
        )
    assert r.status_code == 404

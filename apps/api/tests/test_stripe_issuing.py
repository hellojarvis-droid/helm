"""Stripe Issuing provisioning — flag gating + preconditions + idempotency.

Stripe SDK is fully mocked; we only verify our glue writes the right DB
state and respects the preconditions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from helm.auth import CurrentUser, require_user
from helm.config import get_settings
from helm.db.models import Business, User
from helm.main import create_app
from helm.services import stripe_client
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.conftest import requires_db


@pytest.fixture(autouse=True)
def _enable_issuing(monkeypatch):
    """Flip the flag on for these tests. Individual cases override via
    monkeypatch below when testing the off-path."""
    monkeypatch.setenv("STRIPE_ISSUING_ENABLED", "true")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@requires_db
@pytest.mark.asyncio
async def test_provision_creates_cardholder_and_card(session, monkeypatch) -> None:
    user = User(supabase_id="sub-is-1", email="is1@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle",
        vertical="dtc_physical",
        stripe_account_id="acct_issuing",
        stripe_onboarding_complete=True,
    )
    session.add(biz)
    await session.commit()

    monkeypatch.setattr(
        stripe_client, "create_issuing_cardholder", AsyncMock(return_value="ich_test")
    )
    monkeypatch.setattr(stripe_client, "create_issuing_card", AsyncMock(return_value="ic_test"))

    fake_user = CurrentUser(supabase_id=user.supabase_id, email=user.email, raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/businesses/{biz.id}/stripe/issuing/provision",
            headers={"Authorization": "Bearer stub"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cardholder_id"] == "ich_test"
    assert body["card_id"] == "ic_test"
    assert body["reused_existing"] is False

    # DB (fresh session) reflects the persisted IDs.
    from helm.db.session import get_sessionmaker

    sm = get_sessionmaker()
    async with sm() as s2:
        refreshed = (await s2.execute(select(Business).where(Business.id == biz.id))).scalar_one()
        assert refreshed.stripe_issuing_cardholder_id == "ich_test"
        assert refreshed.stripe_card_id == "ic_test"


@requires_db
@pytest.mark.asyncio
async def test_provision_is_idempotent(session, monkeypatch) -> None:
    user = User(supabase_id="sub-is-2", email="is2@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle",
        vertical="dtc_physical",
        stripe_account_id="acct_yes",
        stripe_onboarding_complete=True,
        stripe_issuing_cardholder_id="ich_existing",
        stripe_card_id="ic_existing",
    )
    session.add(biz)
    await session.commit()

    # Neither Stripe call should fire on re-provision of an already-provisioned business.
    cholder = AsyncMock()
    card = AsyncMock()
    monkeypatch.setattr(stripe_client, "create_issuing_cardholder", cholder)
    monkeypatch.setattr(stripe_client, "create_issuing_card", card)

    fake_user = CurrentUser(supabase_id=user.supabase_id, email=user.email, raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/businesses/{biz.id}/stripe/issuing/provision",
            headers={"Authorization": "Bearer stub"},
        )
    assert r.status_code == 200
    assert r.json()["reused_existing"] is True
    assert r.json()["cardholder_id"] == "ich_existing"
    cholder.assert_not_called()
    card.assert_not_called()


@requires_db
@pytest.mark.asyncio
async def test_provision_requires_onboarding_complete(session) -> None:
    user = User(supabase_id="sub-is-3", email="is3@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle",
        vertical="dtc_physical",
        stripe_account_id="acct_incomplete",
        stripe_onboarding_complete=False,  # ← not onboarded
    )
    session.add(biz)
    await session.commit()

    fake_user = CurrentUser(supabase_id=user.supabase_id, email=user.email, raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/businesses/{biz.id}/stripe/issuing/provision",
            headers={"Authorization": "Bearer stub"},
        )
    assert r.status_code == 409
    assert "onboarding" in r.json()["detail"].lower()


@requires_db
@pytest.mark.asyncio
async def test_provision_503_when_flag_off(session, monkeypatch) -> None:
    monkeypatch.setenv("STRIPE_ISSUING_ENABLED", "false")
    get_settings.cache_clear()

    user = User(supabase_id="sub-is-4", email="is4@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle",
        vertical="dtc_physical",
        stripe_account_id="acct_x",
        stripe_onboarding_complete=True,
    )
    session.add(biz)
    await session.commit()

    fake_user = CurrentUser(supabase_id=user.supabase_id, email=user.email, raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/businesses/{biz.id}/stripe/issuing/provision",
            headers={"Authorization": "Bearer stub"},
        )
    assert r.status_code == 503
    assert "not enabled" in r.json()["detail"].lower()


@requires_db
@pytest.mark.asyncio
async def test_provision_cross_tenant_404(session, monkeypatch) -> None:
    user_a = User(supabase_id="sub-is-a", email="a@example.com", tier="founder")
    user_b = User(supabase_id="sub-is-b", email="b@example.com", tier="founder")
    session.add_all([user_a, user_b])
    await session.flush()
    biz = Business(
        user_id=user_a.id,
        name="A's",
        vertical="dtc_physical",
        stripe_account_id="acct_ap",
        stripe_onboarding_complete=True,
    )
    session.add(biz)
    await session.commit()

    fake_b = CurrentUser(supabase_id=user_b.supabase_id, email=user_b.email, raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_b
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/businesses/{biz.id}/stripe/issuing/provision",
            headers={"Authorization": "Bearer stub"},
        )
    assert r.status_code == 404

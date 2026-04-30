"""Businesses REST — create / list / get, with tenant isolation."""

from __future__ import annotations

import pytest
from helm.auth import CurrentUser, require_user
from helm.db.models import User
from helm.main import create_app
from httpx import ASGITransport, AsyncClient

from tests.conftest import requires_db


@requires_db
@pytest.mark.asyncio
async def test_create_list_get_business(session) -> None:
    user = User(supabase_id="sub-biz-1", email="biz1@example.com", tier="founder")
    session.add(user)
    await session.commit()

    fake_user = CurrentUser(supabase_id="sub-biz-1", email="biz1@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer stub"}

        # Create
        r = await client.post(
            "/businesses",
            json={
                "name": "Candle Co",
                "vertical": "dtc_physical",
                "onboarding": {
                    "idea": "A soy candle studio for renters.",
                    "enabled_specialists": ["Atlas", "Creative Director", "Ads Operator"],
                },
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text
        biz = r.json()
        assert biz["name"] == "Candle Co"
        assert biz["vertical"] == "dtc_physical"
        assert biz["status"] == "initializing"
        assert biz["weekly_spend_cap_cents"] == 50000
        assert biz["brand_kit"]["_onboarding"]["idea"] == "A soy candle studio for renters."
        assert biz["brand_kit"]["_onboarding"]["enabled_specialists"] == [
            "Atlas",
            "Creative Director",
            "Ads Operator",
        ]
        biz_id = biz["id"]

        # List
        r = await client.get("/businesses", headers=headers)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["id"] == biz_id

        # Get
        r = await client.get(f"/businesses/{biz_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["id"] == biz_id

        # Bad vertical
        r = await client.post(
            "/businesses",
            json={"name": "X", "vertical": "nonsense"},
            headers=headers,
        )
        assert r.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_patch_business_updates_caps_and_syncs_stripe(session, monkeypatch) -> None:
    from helm import config
    from helm.db.models import Business, User
    from helm.services import stripe_client as stripe_module

    user = User(supabase_id="sub-patch", email="patch@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle Co",
        vertical="dtc_physical",
        status="active",
        weekly_spend_cap_cents=10_000,
        per_auth_cap_cents=5_000,
        stripe_account_id="acct_test",
        stripe_card_id="ic_test",
    )
    session.add(biz)
    await session.commit()
    biz_id = biz.id

    calls: list[dict[str, object]] = []

    async def _fake_update(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(stripe_module, "update_issuing_caps", _fake_update)
    monkeypatch.setenv("STRIPE_ISSUING_ENABLED", "true")
    config.get_settings.cache_clear()

    fake_user = CurrentUser(supabase_id="sub-patch", email="patch@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.patch(
            f"/businesses/{biz_id}",
            json={"weekly_spend_cap_cents": 75_000, "per_auth_cap_cents": 20_000},
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["weekly_spend_cap_cents"] == 75_000
        assert body["per_auth_cap_cents"] == 20_000
        assert body["stripe_sync"]["synced"] is True

    assert len(calls) == 1
    assert calls[0]["account_id"] == "acct_test"
    assert calls[0]["card_id"] == "ic_test"
    assert calls[0]["weekly_spend_cap_cents"] == 75_000
    assert calls[0]["per_auth_cap_cents"] == 20_000

    config.get_settings.cache_clear()


@requires_db
@pytest.mark.asyncio
async def test_patch_business_mcc_allowlist_override(session, monkeypatch) -> None:
    """Business-level MCC override lands on the row AND pushes to Stripe's
    allowed_categories. reset_mcc_codes_to_default clears it."""
    from helm import config
    from helm.db.models import Business, User
    from helm.services import stripe_client as stripe_module

    user = User(supabase_id="sub-mcc", email="mcc@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="SaaS Co",
        vertical="saas",
        status="active",
        stripe_account_id="acct_mcc",
        stripe_card_id="ic_mcc",
    )
    session.add(biz)
    await session.commit()
    biz_id = biz.id

    calls: list[dict[str, object]] = []

    async def _fake_update(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(stripe_module, "update_issuing_caps", _fake_update)
    monkeypatch.setenv("STRIPE_ISSUING_ENABLED", "true")
    config.get_settings.cache_clear()

    fake = CurrentUser(supabase_id="sub-mcc", email="mcc@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Set a custom allowlist — SaaS business that only needs compute/data MCCs.
        r = await client.patch(
            f"/businesses/{biz_id}",
            json={"allowed_mcc_codes": ["5734", " 7372 ", "5734"]},  # dup + whitespace
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Normalized: stripped + deduped, order preserved.
        assert body["allowed_mcc_codes"] == ["5734", "7372"]
        assert body["stripe_sync"]["synced"] is True

        # Reset back to default.
        r = await client.patch(
            f"/businesses/{biz_id}",
            json={"reset_mcc_codes_to_default": True},
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 200
        assert r.json()["allowed_mcc_codes"] is None

    assert len(calls) == 2
    assert calls[0]["allowed_mcc_codes"] == ["5734", "7372"]
    assert calls[1]["allowed_mcc_codes"] is None  # default allowlist on Stripe side

    config.get_settings.cache_clear()


@requires_db
@pytest.mark.asyncio
async def test_business_isolation_between_users(session) -> None:
    user_a = User(supabase_id="sub-biz-a", email="a@example.com", tier="founder")
    user_b = User(supabase_id="sub-biz-b", email="b@example.com", tier="founder")
    session.add_all([user_a, user_b])
    await session.commit()

    fake_a = CurrentUser(supabase_id="sub-biz-a", email="a@example.com", raw_claims={})
    fake_b = CurrentUser(supabase_id="sub-biz-b", email="b@example.com", raw_claims={})

    app = create_app()
    transport = ASGITransport(app=app)

    # A creates a business.
    app.dependency_overrides[require_user] = lambda: fake_a
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/businesses",
            json={"name": "A's place", "vertical": "dtc_physical"},
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 201
        a_biz_id = r.json()["id"]

    # B tries to read A's business.
    app.dependency_overrides[require_user] = lambda: fake_b
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            f"/businesses/{a_biz_id}",
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 404, "cross-tenant read must 404 (fail-closed)"

        # B's list should be empty.
        r = await client.get("/businesses", headers={"Authorization": "Bearer stub"})
        assert r.json() == []

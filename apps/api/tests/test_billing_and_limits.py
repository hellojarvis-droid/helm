"""Tier limits + /billing/me."""

from __future__ import annotations

import pytest
from helm.auth import CurrentUser, require_user
from helm.db.models import Business, User
from helm.main import create_app
from httpx import ASGITransport, AsyncClient

from tests.conftest import requires_db


@requires_db
@pytest.mark.asyncio
async def test_billing_me_reports_tier_and_usage(session) -> None:
    user = User(supabase_id="sub-bill", email="bill@example.com", tier="founder")
    session.add(user)
    await session.flush()
    for i in range(2):
        session.add(
            Business(
                user_id=user.id,
                name=f"Biz {i}",
                vertical="dtc_physical",
                status="active",
            )
        )
    await session.commit()

    fake = CurrentUser(supabase_id="sub-bill", email="bill@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/billing/me", headers={"Authorization": "Bearer stub"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["tier"] == "founder"
        assert body["display_name"] == "Founder"
        assert body["max_businesses"] == 3
        assert body["businesses_used"] == 2


@requires_db
@pytest.mark.asyncio
async def test_founder_tier_blocks_fourth_business(session) -> None:
    """Founder tier caps at 3 businesses. The 4th POST /businesses must 402."""
    user = User(supabase_id="sub-cap", email="cap@example.com", tier="founder")
    session.add(user)
    await session.flush()
    for i in range(3):
        session.add(
            Business(
                user_id=user.id,
                name=f"Biz {i}",
                vertical="dtc_physical",
                status="active",
            )
        )
    await session.commit()

    fake = CurrentUser(supabase_id="sub-cap", email="cap@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/businesses",
            json={"name": "Fourth", "vertical": "dtc_physical"},
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 402, r.text
        body = r.json()["detail"]
        assert body["error"] == "tier_limit_exceeded"
        assert body["limit"] == "max_businesses"
        assert body["current"] == 3
        assert body["allowed"] == 3


@requires_db
@pytest.mark.asyncio
async def test_portfolio_tier_unlimited_businesses(session) -> None:
    """Portfolio tier has max_businesses=0 (unlimited). The 4th must succeed."""
    user = User(supabase_id="sub-port", email="port@example.com", tier="portfolio")
    session.add(user)
    await session.flush()
    for i in range(3):
        session.add(
            Business(
                user_id=user.id,
                name=f"Biz {i}",
                vertical="dtc_physical",
                status="active",
            )
        )
    await session.commit()

    fake = CurrentUser(supabase_id="sub-port", email="port@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/businesses",
            json={"name": "Fourth", "vertical": "dtc_physical"},
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 201, r.text

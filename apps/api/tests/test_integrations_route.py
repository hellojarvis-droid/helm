"""Integrations route — connect + sync + list, with Composio mocked.

We never hit real Composio in unit tests. `initiate_connection` and
`get_connection` are monkey-patched to deterministic stubs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from helm.auth import CurrentUser, require_user
from helm.db.models import Business, Integration, User
from helm.main import create_app
from helm.services import composio_client
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.conftest import requires_db


@requires_db
@pytest.mark.asyncio
async def test_connect_writes_pending_row(session, monkeypatch) -> None:
    user = User(supabase_id="sub-int-1", email="int1@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="Candle", vertical="dtc_physical")
    session.add(biz)
    await session.commit()

    fake_conn = composio_client.ConnectionRequest(
        connection_id="conn_abc123",
        redirect_url="https://backend.composio.dev/s/auth/abc123",
        status="INITIATED",
    )
    monkeypatch.setattr(composio_client, "initiate_connection", AsyncMock(return_value=fake_conn))

    fake_user = CurrentUser(supabase_id="sub-int-1", email="int1@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/integrations/{biz.id}/connect/gmail",
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["toolkit"] == "gmail"
        assert body["redirect_url"] == fake_conn.redirect_url
        assert body["composio_connection_id"] == "conn_abc123"
        assert body["status"] == "pending"

    # DB row exists with pending status.
    row = (
        await session.execute(select(Integration).where(Integration.business_id == biz.id))
    ).scalar_one()
    assert row.toolkit == "gmail"
    assert row.composio_connection_id == "conn_abc123"
    assert row.status == "pending"


@requires_db
@pytest.mark.asyncio
async def test_sync_flips_to_active_when_upstream_active(session, monkeypatch) -> None:
    user = User(supabase_id="sub-int-2", email="int2@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="Candle", vertical="dtc_physical")
    session.add(biz)
    await session.flush()
    integ = Integration(
        business_id=biz.id,
        toolkit="gmail",
        composio_connection_id="conn_xyz",
        status="pending",
        meta={},
    )
    session.add(integ)
    await session.commit()

    monkeypatch.setattr(
        composio_client,
        "get_connection",
        AsyncMock(return_value={"status": "ACTIVE", "id": "conn_xyz"}),
    )

    fake_user = CurrentUser(supabase_id="sub-int-2", email="int2@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/integrations/{integ.id}/sync",
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "active"


@requires_db
@pytest.mark.asyncio
async def test_reconnect_on_existing_active_returns_409(session, monkeypatch) -> None:
    user = User(supabase_id="sub-int-3", email="int3@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="Candle", vertical="dtc_physical")
    session.add(biz)
    await session.flush()
    integ = Integration(
        business_id=biz.id,
        toolkit="gmail",
        composio_connection_id="conn_already",
        status="active",
        meta={},
    )
    session.add(integ)
    await session.commit()

    # Initiate should NOT be called — 409 short-circuits before we hit Composio.
    mock_init = AsyncMock()
    monkeypatch.setattr(composio_client, "initiate_connection", mock_init)

    fake_user = CurrentUser(supabase_id="sub-int-3", email="int3@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/integrations/{biz.id}/connect/gmail",
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 409

    mock_init.assert_not_called()


@requires_db
@pytest.mark.asyncio
async def test_cross_tenant_sync_404(session, monkeypatch) -> None:
    user_a = User(supabase_id="sub-int-a", email="a@example.com", tier="founder")
    user_b = User(supabase_id="sub-int-b", email="b@example.com", tier="founder")
    session.add_all([user_a, user_b])
    await session.flush()
    biz = Business(user_id=user_a.id, name="A's", vertical="dtc_physical")
    session.add(biz)
    await session.flush()
    integ = Integration(
        business_id=biz.id,
        toolkit="gmail",
        composio_connection_id="conn_private",
        status="active",
        meta={},
    )
    session.add(integ)
    await session.commit()

    fake_b = CurrentUser(supabase_id="sub-int-b", email="b@example.com", raw_claims={})
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_b
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            f"/integrations/{integ.id}/sync",
            headers={"Authorization": "Bearer stub"},
        )
        assert r.status_code == 404

"""Composio webhook: signature verification + status-flip on delivery."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from helm.config import get_settings
from helm.db.models import Business, Integration, User
from helm.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.conftest import requires_db

_WEBHOOK_SECRET = "test-webhook-secret-123"


def _sign(body: bytes) -> str:
    digest = hmac.new(_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture(autouse=True)
def _patch_webhook_secret(monkeypatch):
    """Clear the cached settings and point the secret at a known value so
    signatures we compute in the test match what the route verifies."""
    get_settings.cache_clear()
    monkeypatch.setenv("COMPOSIO_WEBHOOK_SECRET", _WEBHOOK_SECRET)
    yield
    get_settings.cache_clear()


@requires_db
@pytest.mark.asyncio
async def test_webhook_rejects_missing_signature(session) -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/webhooks/composio", json={"type": "whatever"})
    assert r.status_code == 401


@requires_db
@pytest.mark.asyncio
async def test_webhook_rejects_bad_signature(session) -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/composio",
            json={"type": "whatever"},
            headers={"x-composio-signature-256": "sha256=deadbeef"},
        )
    assert r.status_code == 401


@requires_db
@pytest.mark.asyncio
async def test_webhook_flips_integration_to_active_on_connected_event(session) -> None:
    user = User(supabase_id="sub-wh-1", email="wh1@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="Candle", vertical="dtc_physical")
    session.add(biz)
    await session.flush()
    integ = Integration(
        business_id=biz.id,
        toolkit="gmail",
        composio_connection_id="conn_webhook_1",
        status="pending",
        meta={},
    )
    session.add(integ)
    await session.commit()

    payload = {
        "type": "composio.connected_account.created",
        "connection_id": "conn_webhook_1",
        "data": {"status": "ACTIVE"},
    }
    body = json.dumps(payload).encode()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/composio",
            content=body,
            headers={
                "content-type": "application/json",
                "x-composio-signature-256": _sign(body),
            },
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"
    assert r.json()["integration_status"] == "active"

    # The route committed via its own connection; open a fresh session from
    # the engine to observe the write (Supavisor session pooler doesn't share
    # snapshots across connection pools).
    from helm.db.session import get_sessionmaker

    sm = get_sessionmaker()
    async with sm() as s2:
        refreshed = (
            await s2.execute(select(Integration).where(Integration.id == integ.id))
        ).scalar_one()
        assert refreshed.status == "active"
        assert refreshed.meta["last_webhook_event"] == "composio.connected_account.created"


@requires_db
@pytest.mark.asyncio
async def test_webhook_ignores_unknown_connection_id(session) -> None:
    payload = {
        "type": "composio.connected_account.created",
        "connection_id": "conn_not_ours",
        "data": {"status": "ACTIVE"},
    }
    body = json.dumps(payload).encode()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/composio",
            content=body,
            headers={
                "content-type": "application/json",
                "x-composio-signature-256": _sign(body),
            },
        )
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


@requires_db
@pytest.mark.asyncio
async def test_webhook_marks_expired_on_expiration_event(session) -> None:
    user = User(supabase_id="sub-wh-2", email="wh2@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="Candle", vertical="dtc_physical")
    session.add(biz)
    await session.flush()
    integ = Integration(
        business_id=biz.id,
        toolkit="gmail",
        composio_connection_id="conn_expire",
        status="active",
        meta={},
    )
    session.add(integ)
    await session.commit()

    payload = {"type": "composio.connected_account.expired", "connection_id": "conn_expire"}
    body = json.dumps(payload).encode()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/webhooks/composio",
            content=body,
            headers={
                "content-type": "application/json",
                "x-composio-signature-256": _sign(body),
            },
        )
    assert r.status_code == 200
    assert r.json()["integration_status"] == "expired"

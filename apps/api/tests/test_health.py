"""/health smoke test. No DB required — proves the app factory boots and routes."""

from __future__ import annotations

import pytest
from helm.main import create_app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_health_ok() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "helm-api"
    assert "version" in body
    # Trace ID is always stamped by the middleware
    assert "x-trace-id" in response.headers


@pytest.mark.asyncio
async def test_health_trace_id_preserved_when_provided() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"x-trace-id": "abc123"})
    assert response.status_code == 200
    assert response.headers["x-trace-id"] == "abc123"


from tests.conftest import requires_db  # noqa: E402


@requires_db
@pytest.mark.asyncio
async def test_ready_reports_integrations_and_db_ok(session) -> None:
    """/ready probes the DB + reports which integrations are configured.
    Smoke-tests that the body shape matches what monitoring will read."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/ready")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "helm-api"
    assert body["db"] == "ok"
    integrations = body["integrations"]
    # Every key we expect monitors to look for must be present.
    for key in (
        "anthropic",
        "composio",
        "stripe",
        "stripe_issuing",
        "supabase",
        "openai",
        "sentry",
        "langfuse",
    ):
        assert key in integrations, f"/ready should report '{key}'"
        assert isinstance(integrations[key], bool)

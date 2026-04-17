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

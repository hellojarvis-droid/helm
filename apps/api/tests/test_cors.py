"""CORS middleware — preflight + actual cross-origin request.

The web app POSTs to /chat + /businesses + /approvals with Supabase bearer
tokens from a different origin in production (Vercel). CORS needs to
allow the specific origin AND expose our x-trace-id header so the browser
can read it.
"""

from __future__ import annotations

import pytest
from helm.config import get_settings
from helm.main import create_app
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    """Each CORS test runs with a known allowlist. Settings are cached via
    lru_cache so we clear it around each test."""
    monkeypatch.setenv("WEB_ORIGIN_ALLOWLIST", "http://localhost:3000,https://helm.vercel.app")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_preflight_allowed_origin() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.options(
            "/chat",
            headers={
                "origin": "https://helm.vercel.app",
                "access-control-request-method": "POST",
                "access-control-request-headers": "authorization,content-type",
            },
        )
    assert r.status_code in (200, 204)
    assert r.headers["access-control-allow-origin"] == "https://helm.vercel.app"
    assert "authorization" in r.headers["access-control-allow-headers"].lower()
    assert "POST" in r.headers["access-control-allow-methods"].upper()


@pytest.mark.asyncio
async def test_preflight_rejects_unknown_origin() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.options(
            "/chat",
            headers={
                "origin": "https://evil.example.com",
                "access-control-request-method": "POST",
            },
        )
    # Starlette's CORSMiddleware returns 400 for disallowed preflight.
    # The important thing is no ACA-Origin header echoing the bad origin.
    assert r.headers.get("access-control-allow-origin") != "https://evil.example.com"


@pytest.mark.asyncio
async def test_actual_request_receives_allow_origin_header() -> None:
    """A GET from an allowed origin should include ACA-Origin in the response
    so the browser will surface the body to JS."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health", headers={"origin": "http://localhost:3000"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    # Our own trace_id header must be in Access-Control-Expose-Headers or
    # the browser strips it.
    expose = r.headers.get("access-control-expose-headers", "").lower()
    assert "x-trace-id" in expose


@pytest.mark.asyncio
async def test_empty_allowlist_disables_cors(monkeypatch) -> None:
    """If WEB_ORIGIN_ALLOWLIST is empty, no CORS middleware is registered —
    ACA-Origin never comes back. This is the fail-closed default for when
    the env var is forgotten in production."""
    monkeypatch.setenv("WEB_ORIGIN_ALLOWLIST", "")
    get_settings.cache_clear()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health", headers={"origin": "http://localhost:3000"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers

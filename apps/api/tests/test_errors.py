"""Exception-handler smoke tests. No DB required.

Proves that the global handlers in helm.main:
- Normalize HTTPException(detail=<str>) into {"detail": {"message": ..., "trace_id": ...}}
- Preserve dict-shape ClientError detail and stamp trace_id
- Catch unhandled Exception and return a safe message + trace_id,
  never the raw exception text
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from helm.errors import ClientError
from helm.main import create_app
from httpx import ASGITransport, AsyncClient


def _mount_test_routes(app) -> None:  # type: ignore[no-untyped-def]
    @app.get("/_test/boom_str")
    async def boom_str() -> None:
        raise HTTPException(status_code=400, detail="raw message")

    @app.get("/_test/boom_client")
    async def boom_client() -> None:
        raise ClientError(
            "something_specific",
            status_code=409,
            message="Human-readable message here.",
            extra={"hint": "do the other thing"},
        )

    @app.get("/_test/boom_unhandled")
    async def boom_unhandled() -> None:
        raise RuntimeError("leaky internal detail that must not reach the client")


@pytest.mark.asyncio
async def test_http_exception_str_detail_normalized_to_dict() -> None:
    app = create_app()
    _mount_test_routes(app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/_test/boom_str")
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["message"] == "raw message"
    assert body["detail"]["trace_id"]  # non-empty


@pytest.mark.asyncio
async def test_client_error_dict_detail_carries_extra_and_trace_id() -> None:
    app = create_app()
    _mount_test_routes(app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/_test/boom_client")
    assert r.status_code == 409
    body = r.json()
    d = body["detail"]
    assert d["error"] == "something_specific"
    assert d["message"] == "Human-readable message here."
    assert d["hint"] == "do the other thing"
    assert d["trace_id"]


@pytest.mark.asyncio
async def test_unhandled_exception_never_leaks_text() -> None:
    app = create_app()
    _mount_test_routes(app)
    # raise_app_exceptions=False so the transport returns the handler's
    # response instead of re-raising the caught exception to the caller.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/_test/boom_unhandled")
    assert r.status_code == 500
    body = r.json()
    d = body["detail"]
    assert d["error"] == "internal_error"
    assert "leaky internal detail" not in str(body)
    assert "RuntimeError" not in str(body)
    assert d["trace_id"]
    # trace_id also exposed as response header for support workflows
    assert r.headers["x-trace-id"] == d["trace_id"]

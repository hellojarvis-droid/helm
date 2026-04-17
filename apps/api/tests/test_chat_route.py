"""POST /chat — end-to-end with mocked Anthropic + overridden auth.

We don't want unit tests to spend real Anthropic tokens, so the test swaps
`default_runtime()` for one pointed at a stub async client that returns a
canned response. Auth is overridden via FastAPI's dependency override.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest
from helm.agents import runtime as runtime_module
from helm.auth import CurrentUser, require_user
from helm.db.models import AgentEvent, User
from helm.main import create_app
from helm.services.user_sync import sync_user_from_supabase
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.conftest import requires_db


@dataclass
class _StubUsage:
    input_tokens: int = 12
    output_tokens: int = 7


@dataclass
class _StubBlock:
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "text": self.text,
            "id": self.id,
            "name": self.name,
            "input": self.input,
        }


@dataclass
class _StubResponse:
    content: list[_StubBlock]
    stop_reason: str = "end_turn"
    usage: _StubUsage = field(default_factory=_StubUsage)


def _stub_client(response: _StubResponse) -> Any:
    """An async-mock Anthropic client whose `.messages.create(...)` returns
    the given response. Matches the surface MessagesRuntime uses."""
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


async def _read_sse_events(resp_iter: AsyncIterator[bytes]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    buf = b""
    async for chunk in resp_iter:
        buf += chunk
        while b"\n\n" in buf:
            frame, buf = buf.split(b"\n\n", 1)
            for line in frame.splitlines():
                if line.startswith(b"data: "):
                    events.append(json.loads(line[len(b"data: ") :].decode()))
    return events


@requires_db
@pytest.mark.asyncio
async def test_chat_turn_end_to_end(session, monkeypatch) -> None:
    # Seed a user so /chat's sync_user succeeds.
    user = User(supabase_id="sub-chat-1", email="chat1@example.com", tier="founder")
    session.add(user)
    await session.commit()

    fake_user = CurrentUser(supabase_id="sub-chat-1", email="chat1@example.com", raw_claims={})

    # Swap the runtime's anthropic client for a stub.
    stub = _stub_client(
        _StubResponse(
            content=[_StubBlock(type="text", text="hello, founder")],
            stop_reason="end_turn",
        )
    )
    rt = runtime_module.MessagesRuntime(client=stub)
    monkeypatch.setattr(runtime_module, "_default", rt)

    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user

    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as client,
        client.stream(
            "POST", "/chat", json={"message": "hi"}, headers={"Authorization": "Bearer stub"}
        ) as r,
    ):
        assert r.status_code == 200
        events = await _read_sse_events(r.aiter_bytes())

    kinds = [e["kind"] for e in events]
    assert kinds[0] == "user_logged"
    assert "turn_cost" in kinds
    assert kinds[-1] == "done"

    # Event log should have user msg + agent msg at minimum.
    # Open a NEW session here — the one the route used was the request-scoped
    # session that closed when the response finished. We read through the test's
    # own `session` fixture.
    # Ask for all events for this user's CEO session.
    from helm.services.sessions import get_or_create_ceo_session

    # sync_user persisted a user row; fetch it.
    synced = await sync_user_from_supabase(session, fake_user)
    ceo = await get_or_create_ceo_session(session, synced.id)

    rows = (
        (
            await session.execute(
                select(AgentEvent)
                .where(AgentEvent.session_id == ceo.id)
                .order_by(AgentEvent.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    types = [r.event_type for r in rows]
    assert "message.user" in types
    assert "message.agent" in types
    agent_msg = next(r for r in rows if r.event_type == "message.agent")
    assert agent_msg.payload["text"] == "hello, founder"


@requires_db
@pytest.mark.asyncio
async def test_chat_returns_error_when_kill_switch_is_on(session, monkeypatch) -> None:
    from helm.services import kill_switch

    user = User(
        supabase_id="sub-chat-2",
        email="chat2@example.com",
        tier="founder",
        kill_switch_active=True,
    )
    session.add(user)
    await session.commit()
    kill_switch._invalidate_cache_for_tests()

    fake_user = CurrentUser(supabase_id="sub-chat-2", email="chat2@example.com", raw_claims={})

    # Stub won't be called since kill switch fires first.
    stub = _stub_client(_StubResponse(content=[_StubBlock(type="text", text="never")]))
    rt = runtime_module.MessagesRuntime(client=stub)
    monkeypatch.setattr(runtime_module, "_default", rt)

    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user

    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as client,
        client.stream(
            "POST", "/chat", json={"message": "hi"}, headers={"Authorization": "Bearer stub"}
        ) as r,
    ):
        assert r.status_code == 200
        events = await _read_sse_events(r.aiter_bytes())

    # Must surface an error event before any done.
    assert any(e["kind"] == "error" and e.get("reason") == "kill_switch_activated" for e in events)
    stub.messages.create.assert_not_called()

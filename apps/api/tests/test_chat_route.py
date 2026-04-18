"""POST /chat — end-to-end with a stub Anthropic stream + overridden auth.

Session 2 mock uses messages.stream() instead of messages.create(), emits a
single text_delta event, and surfaces the final Message via get_final_message().
Bypasses Pydantic validation via `model_construct` since the real response
shapes carry extra required fields we don't care about in tests.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock

import pytest
from anthropic.types import (
    Message,
    RawContentBlockDeltaEvent,
    TextBlock,
    TextDelta,
    ToolUseBlock,
    Usage,
)
from helm.agents import runtime as runtime_module
from helm.auth import CurrentUser, require_user
from helm.db.models import AgentEvent, User
from helm.main import create_app
from helm.services.user_sync import sync_user_from_supabase
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.conftest import requires_db

# ────────────────────────────────────────────────────────────────────
# Mock Anthropic stream client
# ────────────────────────────────────────────────────────────────────


def _stub_stream_client(
    *,
    text: str = "",
    tool_uses: list[dict[str, Any]] | None = None,
    stop_reason: str = "end_turn",
) -> Any:
    """Returns an object that mimics AsyncAnthropic for `.messages.stream()` use.

    Second calls (after a tool round-trip) reuse the same configured response —
    tests should pass a list of responses via `_SequenceStreamClient` for multi-turn.
    """
    tool_uses = tool_uses or []
    content: list[Any] = []
    if text:
        content.append(TextBlock(type="text", text=text, citations=None))
    for tu in tool_uses:
        content.append(
            ToolUseBlock(type="tool_use", id=tu["id"], name=tu["name"], input=tu.get("input", {}))
        )

    final = Message.model_construct(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-opus-4-7",
        content=content,
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=Usage.model_construct(input_tokens=10, output_tokens=5),
    )

    class _FakeStream:
        async def __aenter__(self) -> _FakeStream:
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def __aiter__(self) -> AsyncIterator[Any]:
            # Emit a single text_delta event if there's text, to exercise streaming path.
            if text:
                yield RawContentBlockDeltaEvent.model_construct(
                    type="content_block_delta",
                    index=0,
                    delta=TextDelta.model_construct(type="text_delta", text=text),
                )

        async def get_final_message(self) -> Message:
            return final

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(return_value=_FakeStream())
    return client


class _SequenceStreamClient:
    """Multi-turn stub: each call to .messages.stream() pops the next response."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.call_count = 0
        self.messages = self  # duck-type `client.messages.stream`

    def stream(self, **kwargs: Any) -> Any:
        idx = min(self.call_count, len(self.responses) - 1)
        self.call_count += 1
        r = self.responses[idx]
        client = _stub_stream_client(**r)
        return client.messages.stream()


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


# ────────────────────────────────────────────────────────────────────
# Tests
# ────────────────────────────────────────────────────────────────────


@requires_db
@pytest.mark.asyncio
async def test_chat_turn_end_to_end(session, monkeypatch) -> None:
    user = User(supabase_id="sub-chat-1", email="chat1@example.com", tier="founder")
    session.add(user)
    await session.commit()

    fake_user = CurrentUser(supabase_id="sub-chat-1", email="chat1@example.com", raw_claims={})

    stub = _stub_stream_client(text="hello, founder", stop_reason="end_turn")
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
    assert "text_delta" in kinds
    text_events = [e for e in events if e["kind"] == "text_delta"]
    assert text_events[0]["text"] == "hello, founder"
    assert "turn_cost" in kinds
    assert kinds[-1] == "done"

    # Verify persistence of both messages.
    from helm.services.sessions import get_or_create_ceo_session

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
    stub = _stub_stream_client(text="never", stop_reason="end_turn")
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

    assert any(e["kind"] == "error" and e.get("reason") == "kill_switch_activated" for e in events)
    stub.messages.stream.assert_not_called()


@requires_db
@pytest.mark.asyncio
async def test_chat_delegates_to_stub_specialist(session, monkeypatch) -> None:
    """CEO calls delegate_to_specialist → stub returns 'not_implemented' → CEO relays."""
    user = User(supabase_id="sub-chat-3", email="chat3@example.com", tier="founder")
    session.add(user)
    await session.commit()

    fake_user = CurrentUser(supabase_id="sub-chat-3", email="chat3@example.com", raw_claims={})

    # Turn 1: CEO responds with tool_use calling ads_operator (still stubbed).
    # Turn 2: CEO responds with text to the user using the stub's response.
    # We pick ads_operator intentionally because product_builder is now real
    # and would attempt an Anthropic call — stubs stay instant + zero-cost.
    seq = _SequenceStreamClient(
        responses=[
            {
                "text": "",
                "tool_uses": [
                    {
                        "id": "tu_1",
                        "name": "delegate_to_specialist",
                        "input": {
                            "specialist_name": "ads_operator",
                            "task": "plan a Meta launch campaign",
                        },
                    }
                ],
                "stop_reason": "tool_use",
            },
            {
                "text": "Ads Operator isn't online yet — here's what it would do: (relayed)",
                "stop_reason": "end_turn",
            },
        ]
    )
    rt = runtime_module.MessagesRuntime(client=seq)  # type: ignore[arg-type]
    monkeypatch.setattr(runtime_module, "_default", rt)

    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user

    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as client,
        client.stream(
            "POST",
            "/chat",
            json={"message": "launch a candle store"},
            headers={"Authorization": "Bearer stub"},
        ) as r,
    ):
        assert r.status_code == 200
        events = await _read_sse_events(r.aiter_bytes())

    kinds = [e["kind"] for e in events]
    # Expect tool_call → tool_result → then text_delta of the relay.
    assert "tool_call" in kinds
    assert "tool_result" in kinds

    tool_call_event = next(e for e in events if e["kind"] == "tool_call")
    assert tool_call_event["name"] == "delegate_to_specialist"
    assert tool_call_event["input"]["specialist_name"] == "product_builder"

    # The specialist's completion should be in the event log.
    from helm.services.sessions import get_or_create_ceo_session

    synced = await sync_user_from_supabase(session, fake_user)
    ceo = await get_or_create_ceo_session(session, synced.id)
    rows = (
        (
            await session.execute(
                select(AgentEvent)
                .where(AgentEvent.session_id == ceo.id)
                .where(AgentEvent.event_type == "specialist_completed")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].agent_name == "ads_operator"
    assert rows[0].payload["status"] == "not_implemented"


@requires_db
@pytest.mark.asyncio
async def test_request_user_approval_creates_row_and_emits_event(session, monkeypatch) -> None:
    from helm.db.models import Approval, Business

    user = User(supabase_id="sub-chat-4", email="chat4@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="Test Candles", vertical="dtc_physical")
    session.add(biz)
    await session.commit()
    biz_id = biz.id

    fake_user = CurrentUser(supabase_id="sub-chat-4", email="chat4@example.com", raw_claims={})

    seq = _SequenceStreamClient(
        responses=[
            {
                "text": "",
                "tool_uses": [
                    {
                        "id": "tu_approval",
                        "name": "request_user_approval",
                        "input": {
                            "kind": "spend",
                            "summary": "Spend $340 on 3 TikTok creatives.",
                            "business_id": str(biz_id),
                            "details": {
                                "amount_cents": 34000,
                                "merchant_hint": "TikTok Ads",
                                "purpose": "3 creatives targeting 25-34 home-decor",
                            },
                        },
                    }
                ],
                "stop_reason": "tool_use",
            },
            {"text": "Asked for approval.", "stop_reason": "end_turn"},
        ]
    )
    rt = runtime_module.MessagesRuntime(client=seq)  # type: ignore[arg-type]
    monkeypatch.setattr(runtime_module, "_default", rt)

    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user

    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as client,
        client.stream(
            "POST",
            "/chat",
            json={"message": "spend money"},
            headers={"Authorization": "Bearer stub"},
        ) as r,
    ):
        assert r.status_code == 200
        events = await _read_sse_events(r.aiter_bytes())

    # SSE must surface an approval_requested event — with details so the
    # client can render a money-aware card without a follow-up fetch.
    approval_events = [e for e in events if e["kind"] == "approval_requested"]
    assert len(approval_events) == 1
    assert approval_events[0]["approval_kind"] == "spend"
    assert approval_events[0]["business_id"] == str(biz_id)
    assert approval_events[0]["details"]["amount_cents"] == 34000
    assert approval_events[0]["details"]["merchant_hint"] == "TikTok Ads"

    # DB must have the approvals row.
    rows = (
        (await session.execute(select(Approval).where(Approval.business_id == biz_id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].status == "pending"
    assert rows[0].kind == "spend"
    assert "TikTok" in rows[0].summary

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
from helm.db.models import AgentEvent, AgentSession, Business, User
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
async def test_chat_history_returns_shared_thread_events(session) -> None:
    user = User(supabase_id="sub-chat-history", email="history@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="Candle", vertical="dtc_physical")
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=None, status="active")
    session.add(ag)
    await session.flush()
    session.add_all(
        [
            AgentEvent(
                session_id=ag.id,
                business_id=biz.id,
                event_type="message.user",
                agent_name="user",
                payload={"text": "What needs my approval?"},
            ),
            AgentEvent(
                session_id=ag.id,
                business_id=biz.id,
                event_type="message.agent",
                agent_name="ceo_agent",
                payload={"text": "One launch spend is waiting.", "content_blocks": []},
            ),
            AgentEvent(
                session_id=ag.id,
                business_id=biz.id,
                event_type="approval_requested",
                agent_name="ceo_agent",
                payload={
                    "approval_id": "00000000-0000-0000-0000-000000000001",
                    "kind": "spend",
                    "summary": "Approve first-week ad budget.",
                },
            ),
        ]
    )
    await session.commit()

    fake_user = CurrentUser(
        supabase_id="sub-chat-history", email="history@example.com", raw_claims={}
    )
    app = create_app()
    app.dependency_overrides[require_user] = lambda: fake_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/chat/history", headers={"Authorization": "Bearer stub"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"] == str(ag.id)
    assert [item["kind"] for item in body["items"]] == [
        "message.user",
        "message.agent",
        "approval_requested",
    ]
    assert body["items"][0]["role"] == "user"
    assert body["items"][0]["text"] == "What needs my approval?"
    assert body["items"][1]["role"] == "agent"
    assert body["items"][1]["text"] == "One launch spend is waiting."
    assert body["items"][2]["approval"]["summary"] == "Approve first-week ad budget."


@requires_db
@pytest.mark.asyncio
async def test_load_history_strips_historical_tool_use_blocks(session) -> None:
    user = User(supabase_id="sub-chat-replay", email="replay@example.com", tier="founder")
    session.add(user)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=None, status="active")
    session.add(ag)
    await session.flush()
    session.add_all(
        [
            AgentEvent(
                session_id=ag.id,
                business_id=None,
                event_type="message.user",
                agent_name="user",
                payload={"text": "Ask finance to reconcile charges."},
            ),
            AgentEvent(
                session_id=ag.id,
                business_id=None,
                event_type="message.agent",
                agent_name="ceo_agent",
                payload={
                    "text": "",
                    "content_blocks": [
                        {
                            "type": "tool_use",
                            "id": "tu_old",
                            "name": "delegate_to_specialist",
                            "input": {"specialist_name": "finance_ops", "task": "reconcile"},
                        }
                    ],
                },
            ),
            AgentEvent(
                session_id=ag.id,
                business_id=None,
                event_type="tool_result",
                agent_name="ceo_agent",
                payload={"name": "delegate_to_specialist", "result": {"status": "ok"}},
            ),
        ]
    )
    await session.commit()

    rt = runtime_module.MessagesRuntime(client=_stub_stream_client(text="ok"))
    history = await rt._load_history(session, ag.id)

    assert history[0] == {"role": "user", "content": "Ask finance to reconcile charges."}
    assistant = history[1]
    assert assistant["role"] == "assistant"
    assert all(block.get("type") != "tool_use" for block in assistant["content"])
    assert assistant["content"][0]["type"] == "text"
    assert "completed" in assistant["content"][0]["text"]


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
    """CEO calls delegate_to_specialist → stub returns 'not_implemented' → CEO relays.

    All 8 production specialists are real LLMSpecialists now — they'd all try
    to hit Anthropic in CI. We register a synthetic stub for the duration of
    this test to exercise the CEO→delegate→stub_response→relay flow without
    network.
    """
    # Every production specialist is a real LLMSpecialist; swap in a synthetic
    # StubSpecialist for the duration of this test so no network is needed.
    from helm.agents.specialists import base as specialists_base

    stub = specialists_base.StubSpecialist(
        name="finance_ops",
        persona_note="Finance & Ops",
        what_i_would_do="reconcile charges and flag anomalies (test stub)",
    )
    monkeypatch.setitem(specialists_base._REGISTRY, "finance_ops", stub)

    user = User(supabase_id="sub-chat-3", email="chat3@example.com", tier="founder")
    session.add(user)
    await session.commit()

    fake_user = CurrentUser(supabase_id="sub-chat-3", email="chat3@example.com", raw_claims={})

    # Turn 1: CEO responds with tool_use calling the test stub.
    # Turn 2: CEO responds with text to the user using the stub's response.
    seq = _SequenceStreamClient(
        responses=[
            {
                "text": "",
                "tool_uses": [
                    {
                        "id": "tu_1",
                        "name": "delegate_to_specialist",
                        "input": {
                            "specialist_name": "finance_ops",
                            "task": "reconcile yesterday's charges",
                        },
                    }
                ],
                "stop_reason": "tool_use",
            },
            {
                "text": "Finance & Ops isn't online yet — here's what it would do: (relayed)",
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
    assert tool_call_event["input"]["specialist_name"] == "finance_ops"

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
    assert rows[0].agent_name == "finance_ops"
    assert rows[0].payload["status"] == "not_implemented"


@requires_db
@pytest.mark.asyncio
async def test_delegate_to_specialist_rejects_foreign_business(session, monkeypatch) -> None:
    from helm.agents.specialists import base as specialists_base
    from helm.agents.tools import ToolContext, _delegate_to_specialist

    stub = specialists_base.StubSpecialist(
        name="finance_ops",
        persona_note="Finance & Ops",
        what_i_would_do="reconcile charges",
    )
    monkeypatch.setitem(specialists_base._REGISTRY, "finance_ops", stub)

    owner = User(supabase_id="sub-owner", email="owner@example.com", tier="founder")
    caller = User(supabase_id="sub-caller", email="caller@example.com", tier="founder")
    session.add_all([owner, caller])
    await session.flush()
    foreign_biz = Business(user_id=owner.id, name="Owner Co", vertical="dtc_physical")
    session.add(foreign_biz)
    await session.flush()
    caller_session = AgentSession(user_id=caller.id, business_id=None, status="active")
    session.add(caller_session)
    await session.commit()

    ctx = ToolContext(
        db=session,
        session_id=caller_session.id,
        user_id=caller.id,
        business_id=None,
    )
    result = await _delegate_to_specialist(
        ctx,
        {
            "specialist_name": "finance_ops",
            "task": "reconcile the other user's charges",
            "business_id": str(foreign_biz.id),
        },
    )

    assert result["status"] == "error"
    assert "business not found" in result["summary"]
    rows = (
        (
            await session.execute(
                select(AgentEvent).where(AgentEvent.event_type == "specialist_completed")
            )
        )
        .scalars()
        .all()
    )
    assert rows == []


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

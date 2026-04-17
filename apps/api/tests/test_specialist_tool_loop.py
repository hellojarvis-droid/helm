"""LLMSpecialist tool-use loop — native + Composio tool dispatch.

Tests exercise the full loop with Anthropic mocked: the model emits a
tool_use block; the specialist routes it (Composio or error); the next
LLM call gets the tool_result; the final text comes through.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from anthropic.types import TextBlock, ToolUseBlock, Usage
from helm.agents.specialists.base import BusinessContext, LLMSpecialist
from helm.db.models import AgentEvent, AgentSession, User
from helm.services import kill_switch
from sqlalchemy import select

from tests.conftest import requires_db


@dataclass
class _Msg:
    content: list[Any]
    stop_reason: str
    usage: Usage
    model: str = "claude-sonnet-4-6"


def _client_with_responses(responses: list[_Msg]) -> Any:
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = AsyncMock(side_effect=responses)
    return client


def _text(text: str) -> TextBlock:
    return TextBlock(type="text", text=text, citations=None)


def _tool_use(id: str, name: str, input: dict) -> ToolUseBlock:
    return ToolUseBlock(type="tool_use", id=id, name=name, input=input)


def _prime_kill_switch(user_id: uuid.UUID) -> None:
    kill_switch._cache[user_id] = kill_switch._CacheEntry(active=False, fetched_at=time.monotonic())


@requires_db
@pytest.mark.asyncio
async def test_loop_dispatches_composio_tool_and_logs_events(session) -> None:
    # Need a real user + session so event_log.write can FK-insert.
    user = User(supabase_id="sub-tl-1", email="tl1@example.com", tier="founder")
    session.add(user)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=None, status="active")
    session.add(ag)
    await session.commit()

    ctx = BusinessContext(
        user_id=user.id,
        business_id=None,
        session_id=ag.id,
        connected_integrations=("reddit",),
    )
    _prime_kill_switch(ctx.user_id)

    # Two-turn sequence: first turn emits tool_use, second returns final text.
    responses = [
        _Msg(
            content=[_tool_use("tu_1", "REDDIT_SEARCH_POSTS", {"query": "candles"})],
            stop_reason="tool_use",
            usage=Usage.model_construct(input_tokens=50, output_tokens=10),
        ),
        _Msg(
            content=[_text("Found 12 Reddit posts about candle commerce.")],
            stop_reason="end_turn",
            usage=Usage.model_construct(input_tokens=80, output_tokens=15),
        ),
    ]
    client = _client_with_responses(responses)

    spec = LLMSpecialist(
        name="test_specialist",
        model="claude-sonnet-4-6",
        system_prompt="Use reddit.",
        tools=[],
        composio_toolkits=["reddit"],
        client=client,
    )

    # Stub Composio list_tools + execute_tool.
    fake_tool = {
        "slug": "REDDIT_SEARCH_POSTS",
        "description": "Search posts on Reddit.",
        "input_parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
    }
    fake_exec_result = {"posts": [{"title": "candles rising", "upvotes": 1200}]}

    with (
        patch(
            "helm.services.composio_client.list_tools",
            new=AsyncMock(return_value=[fake_tool]),
        ),
        patch(
            "helm.services.composio_client.execute_tool",
            new=AsyncMock(return_value=fake_exec_result),
        ) as exec_mock,
    ):
        result = await spec.run(db=session, ctx=ctx, task="Find candle trends on Reddit")

    assert result.status == "ok"
    assert "Reddit" in result.summary
    assert result.metadata["composio_tools_available"] is True
    # Composio execute was called once with the Reddit search slug + args.
    exec_mock.assert_awaited_once()
    call_kwargs = exec_mock.call_args.kwargs
    assert call_kwargs["tool_slug"] == "REDDIT_SEARCH_POSTS"
    assert call_kwargs["arguments"] == {"query": "candles"}

    # Event log holds a tool_call + tool_result for the specialist.
    rows = (
        (
            await session.execute(
                select(AgentEvent)
                .where(AgentEvent.session_id == ag.id)
                .where(AgentEvent.agent_name == "test_specialist")
            )
        )
        .scalars()
        .all()
    )
    types = [r.event_type for r in rows]
    assert "tool_call" in types
    assert "tool_result" in types
    tr = next(r for r in rows if r.event_type == "tool_result")
    assert tr.payload["name"] == "REDDIT_SEARCH_POSTS"
    assert tr.payload["is_error"] is False


@requires_db
@pytest.mark.asyncio
async def test_loop_reports_error_for_unknown_client_side_tool(session) -> None:
    user = User(supabase_id="sub-tl-2", email="tl2@example.com", tier="founder")
    session.add(user)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=None, status="active")
    session.add(ag)
    await session.commit()

    ctx = BusinessContext(user_id=user.id, business_id=None, session_id=ag.id)
    _prime_kill_switch(ctx.user_id)

    # Model invents a tool name we didn't register.
    responses = [
        _Msg(
            content=[_tool_use("tu_1", "IMAGINARY_TOOL", {})],
            stop_reason="tool_use",
            usage=Usage.model_construct(input_tokens=50, output_tokens=10),
        ),
        _Msg(
            content=[_text("Sorry, can't use that tool.")],
            stop_reason="end_turn",
            usage=Usage.model_construct(input_tokens=60, output_tokens=10),
        ),
    ]
    client = _client_with_responses(responses)
    spec = LLMSpecialist(
        name="test_specialist_2",
        model="claude-sonnet-4-6",
        system_prompt="Try tools.",
        client=client,
    )

    result = await spec.run(db=session, ctx=ctx, task="try tools")
    assert result.status == "ok"

    # The tool_result should reflect is_error=True.
    rows = (
        (
            await session.execute(
                select(AgentEvent)
                .where(AgentEvent.session_id == ag.id)
                .where(AgentEvent.agent_name == "test_specialist_2")
                .where(AgentEvent.event_type == "tool_result")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].payload["is_error"] is True


@requires_db
@pytest.mark.asyncio
async def test_loop_without_composio_toolkits_does_not_call_list_tools(session) -> None:
    user = User(supabase_id="sub-tl-3", email="tl3@example.com", tier="founder")
    session.add(user)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=None, status="active")
    session.add(ag)
    await session.commit()

    ctx = BusinessContext(user_id=user.id, business_id=None, session_id=ag.id)
    _prime_kill_switch(ctx.user_id)

    responses = [
        _Msg(
            content=[_text("no tools needed")],
            stop_reason="end_turn",
            usage=Usage.model_construct(input_tokens=20, output_tokens=5),
        ),
    ]
    client = _client_with_responses(responses)
    spec = LLMSpecialist(
        name="plain_specialist",
        model="claude-sonnet-4-6",
        system_prompt="hi",
        client=client,
    )

    list_mock = AsyncMock()
    with patch("helm.services.composio_client.list_tools", new=list_mock):
        result = await spec.run(db=session, ctx=ctx, task="hi")

    assert result.status == "ok"
    list_mock.assert_not_called()
    assert result.metadata["composio_tools_available"] is False


@requires_db
@pytest.mark.asyncio
async def test_loop_skips_toolkits_not_in_connected_integrations(session) -> None:
    """Specialist declares reddit+hackernews; business has only hackernews.
    list_tools must be called with ['hackernews'] only."""
    user = User(supabase_id="sub-tl-4", email="tl4@example.com", tier="founder")
    session.add(user)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=None, status="active")
    session.add(ag)
    await session.commit()

    ctx = BusinessContext(
        user_id=user.id,
        business_id=None,
        session_id=ag.id,
        connected_integrations=("hackernews",),
    )
    _prime_kill_switch(ctx.user_id)

    responses = [
        _Msg(
            content=[_text("done")],
            stop_reason="end_turn",
            usage=Usage.model_construct(input_tokens=20, output_tokens=5),
        )
    ]
    client = _client_with_responses(responses)
    spec = LLMSpecialist(
        name="researcher",
        model="claude-sonnet-4-6",
        system_prompt="research",
        composio_toolkits=["reddit", "hackernews", "product_hunt"],
        client=client,
    )

    list_mock = AsyncMock(return_value=[])
    with patch("helm.services.composio_client.list_tools", new=list_mock):
        await spec.run(db=session, ctx=ctx, task="research")

    list_mock.assert_awaited_once()
    kwargs = list_mock.call_args.kwargs
    assert kwargs["toolkits"] == ["hackernews"]


@requires_db
@pytest.mark.asyncio
async def test_kill_switch_aborts_mid_loop(session) -> None:
    user = User(supabase_id="sub-tl-5", email="tl5@example.com", tier="founder")
    session.add(user)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=None, status="active")
    session.add(ag)
    await session.commit()

    ctx = BusinessContext(user_id=user.id, business_id=None, session_id=ag.id)
    # Flip kill switch ON. assert_not_set will raise on the first check.
    kill_switch._cache[ctx.user_id] = kill_switch._CacheEntry(
        active=True, fetched_at=time.monotonic()
    )

    client = _client_with_responses([])  # should never be called
    spec = LLMSpecialist(
        name="blocked",
        model="claude-sonnet-4-6",
        system_prompt="hi",
        client=client,
    )

    with pytest.raises(kill_switch.KillSwitchActivated):
        await spec.run(db=session, ctx=ctx, task="hi")

    client.messages.create.assert_not_called()

    # Clean up for subsequent tests.
    kill_switch._invalidate_cache_for_tests()

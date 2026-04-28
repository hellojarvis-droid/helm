"""LLMSpecialist computer-use escalation — opt-in tool inserts a row.

Mirrors test_specialist_tool_loop.py's mocking pattern. Verifies:
  * a specialist with `can_escalate_to_computer_use=True` exposes the tool
  * the dispatcher inserts a `computer_use_escalations` row with the
    specialist's name as requester and the ctx.business_id (not the model's)
  * a specialist without the flag rejects the tool with an error
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest
from anthropic.types import TextBlock, ToolUseBlock, Usage
from helm.agents.specialists.base import BusinessContext, LLMSpecialist
from helm.db.models import AgentEvent, AgentSession, Business, ComputerUseEscalation, User
from helm.services import kill_switch
from sqlalchemy import select

from tests.conftest import requires_db


@dataclass
class _Msg:
    content: list[Any]
    stop_reason: str
    usage: Usage
    model: str = "claude-sonnet-4-6"


def _client_with(responses: list[_Msg]) -> Any:
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = AsyncMock(side_effect=responses)
    return client


def _prime(user_id: uuid.UUID) -> None:
    kill_switch._cache[user_id] = kill_switch._CacheEntry(active=False, fetched_at=time.monotonic())


@requires_db
@pytest.mark.asyncio
async def test_specialist_escalates_to_computer_use(session) -> None:
    user = User(supabase_id="sub-spe", email="spe@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="Candle", vertical="dtc_physical")
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.commit()
    _prime(user.id)

    ctx = BusinessContext(user_id=user.id, business_id=biz.id, session_id=ag.id)

    responses = [
        _Msg(
            content=[
                ToolUseBlock(
                    type="tool_use",
                    id="tu_1",
                    name="escalate_to_computer_use",
                    input={
                        "task": "Create a $20/day TikTok spark ad",
                        "app_hint": "tiktok ads manager",
                    },
                )
            ],
            stop_reason="tool_use",
            usage=Usage.model_construct(input_tokens=40, output_tokens=8),
        ),
        _Msg(
            content=[TextBlock(type="text", text="Queued for the desktop.", citations=None)],
            stop_reason="end_turn",
            usage=Usage.model_construct(input_tokens=60, output_tokens=12),
        ),
    ]

    spec = LLMSpecialist(
        name="ads_operator",
        model="claude-sonnet-4-6",
        system_prompt="Run paid ads.",
        can_escalate_to_computer_use=True,
        client=_client_with(responses),
    )

    result = await spec.run(db=session, ctx=ctx, task="Launch a TikTok small-budget spark ad.")
    assert result.status == "ok"

    rows = (await session.execute(select(ComputerUseEscalation))).scalars().all()
    assert len(rows) == 1
    assert rows[0].requester == "ads_operator"
    assert rows[0].business_id == biz.id
    assert rows[0].status == "queued"
    assert "TikTok" in rows[0].task

    # tool_result event in the event log records the escalation_id, not just an error.
    tr = (
        (
            await session.execute(
                select(AgentEvent).where(
                    AgentEvent.session_id == ag.id,
                    AgentEvent.event_type == "tool_result",
                    AgentEvent.agent_name == "ads_operator",
                )
            )
        )
        .scalars()
        .one()
    )
    assert tr.payload["is_error"] is False
    assert tr.payload["result"]["status"] == "queued"


@requires_db
@pytest.mark.asyncio
async def test_specialist_without_flag_rejects_tool(session) -> None:
    user = User(supabase_id="sub-spe-2", email="spe2@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="Candle2", vertical="dtc_physical")
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.commit()
    _prime(user.id)

    ctx = BusinessContext(user_id=user.id, business_id=biz.id, session_id=ag.id)

    responses = [
        _Msg(
            content=[
                ToolUseBlock(
                    type="tool_use",
                    id="tu_1",
                    name="escalate_to_computer_use",
                    input={"task": "x", "app_hint": "y"},
                )
            ],
            stop_reason="tool_use",
            usage=Usage.model_construct(input_tokens=30, output_tokens=5),
        ),
        _Msg(
            content=[TextBlock(type="text", text="ok", citations=None)],
            stop_reason="end_turn",
            usage=Usage.model_construct(input_tokens=40, output_tokens=5),
        ),
    ]

    spec = LLMSpecialist(
        name="creative_director",
        model="claude-sonnet-4-6",
        system_prompt="Make brand kits.",
        # can_escalate_to_computer_use NOT set → tool isn't exposed; if the
        # model fabricates a call, the dispatcher returns an error result.
        client=_client_with(responses),
    )

    await spec.run(db=session, ctx=ctx, task="t")

    rows = (await session.execute(select(ComputerUseEscalation))).scalars().all()
    assert len(rows) == 0

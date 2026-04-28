"""escalate_to_computer_use CEO tool — escalation row + audit event."""

from __future__ import annotations

import time
import uuid

import pytest
from helm.agents.tools import ToolContext, _escalate_to_computer_use
from helm.db.models import AgentEvent, AgentSession, Business, ComputerUseEscalation, User
from helm.services import kill_switch
from sqlalchemy import select

from tests.conftest import requires_db


def _prime(user_id: uuid.UUID) -> None:
    kill_switch._cache[user_id] = kill_switch._CacheEntry(active=False, fetched_at=time.monotonic())


@requires_db
@pytest.mark.asyncio
async def test_escalate_inserts_row_and_event(session) -> None:
    user = User(supabase_id="sub-esc", email="esc@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="Candle", vertical="dtc_physical")
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.commit()
    _prime(user.id)

    ctx = ToolContext(db=session, session_id=ag.id, user_id=user.id, business_id=biz.id)
    result = await _escalate_to_computer_use(
        ctx,
        {
            "business_id": str(biz.id),
            "task": "Open TikTok Ads Manager and create a $20/day spark ad.",
            "app_hint": "tiktok ads manager",
        },
    )

    assert result["status"] == "queued"
    assert "escalation_id" in result

    row = (
        (await session.execute(select(ComputerUseEscalation))).scalars().one()
    )
    assert row.requester == "ceo_agent"
    assert row.status == "queued"
    assert row.app_hint == "tiktok ads manager"
    assert "TikTok" in row.task

    events = (
        (
            await session.execute(
                select(AgentEvent).where(AgentEvent.event_type == "computer_use_requested")
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["escalation_id"] == str(row.id)


@requires_db
@pytest.mark.asyncio
async def test_escalate_rejects_foreign_business(session) -> None:
    user_a = User(supabase_id="sub-esc-a", email="ea@example.com", tier="founder")
    user_b = User(supabase_id="sub-esc-b", email="eb@example.com", tier="founder")
    session.add_all([user_a, user_b])
    await session.flush()
    biz_a = Business(user_id=user_a.id, name="A", vertical="dtc_physical")
    session.add(biz_a)
    await session.flush()
    ag = AgentSession(user_id=user_b.id, business_id=None, status="active")
    session.add(ag)
    await session.commit()

    ctx = ToolContext(db=session, session_id=ag.id, user_id=user_b.id, business_id=None)
    result = await _escalate_to_computer_use(
        ctx,
        {
            "business_id": str(biz_a.id),
            "task": "noop",
            "app_hint": "noop",
        },
    )
    assert result["status"] == "error"
    assert "not found" in result["summary"]

    rows = (await session.execute(select(ComputerUseEscalation))).scalars().all()
    assert len(rows) == 0


@requires_db
@pytest.mark.asyncio
async def test_escalate_validates_inputs(session) -> None:
    user = User(supabase_id="sub-esc-v", email="ev@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="X", vertical="dtc_physical")
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.commit()

    ctx = ToolContext(db=session, session_id=ag.id, user_id=user.id, business_id=biz.id)

    r1 = await _escalate_to_computer_use(ctx, {"task": "x", "app_hint": "y"})
    assert r1["status"] == "error"
    r2 = await _escalate_to_computer_use(
        ctx, {"business_id": "not-a-uuid", "task": "x", "app_hint": "y"}
    )
    assert r2["status"] == "error"
    r3 = await _escalate_to_computer_use(
        ctx, {"business_id": str(biz.id), "task": "", "app_hint": "y"}
    )
    assert r3["status"] == "error"
    r4 = await _escalate_to_computer_use(
        ctx, {"business_id": str(biz.id), "task": "x", "app_hint": ""}
    )
    assert r4["status"] == "error"

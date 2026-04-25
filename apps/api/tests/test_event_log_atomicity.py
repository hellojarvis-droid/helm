"""Atomicity: state mutations and their audit events commit together.

Per CLAUDE.md hard rule #4 ("Every agent action is logged. Event-sourced.")
a crash between writing the state row and writing the audit event must not
leave un-audited state. The tool impls flush + write the event with
commit=False + commit once; if the event-log write raises, the state row
must roll back too.
"""

from __future__ import annotations

import uuid

import pytest
from helm.agents import tools as tools_module
from helm.agents.tools import (
    ToolContext,
    _create_business,
    _request_user_approval,
)
from helm.db.models import AgentEvent, AgentSession, Approval, Business, User
from sqlalchemy import select

from tests.conftest import requires_db


async def _seed_user_and_session(session) -> tuple[User, AgentSession]:
    user = User(supabase_id=f"sub-atom-{uuid.uuid4()}", email="atom@example.com", tier="founder")
    session.add(user)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=None, status="active")
    session.add(ag)
    await session.commit()
    return user, ag


@requires_db
@pytest.mark.asyncio
async def test_create_business_rolls_back_when_event_log_fails(session, monkeypatch) -> None:
    user, ag = await _seed_user_and_session(session)

    async def boom(*args, **kwargs):
        raise RuntimeError("simulated event_log failure")

    monkeypatch.setattr(tools_module.event_log, "write", boom)

    ctx = ToolContext(db=session, session_id=ag.id, user_id=user.id, business_id=None)

    with pytest.raises(RuntimeError, match="simulated event_log failure"):
        await _create_business(
            ctx,
            {"name": "Doomed Co", "vertical": "dtc_physical", "weekly_spend_cap_cents": 12345},
        )

    await session.rollback()
    rows = (await session.execute(select(Business).where(Business.user_id == user.id))).all()
    assert rows == [], "Business row leaked despite event_log failure"


@requires_db
@pytest.mark.asyncio
async def test_request_user_approval_rolls_back_when_event_log_fails(
    session, monkeypatch
) -> None:
    user, ag = await _seed_user_and_session(session)

    biz = Business(user_id=user.id, name="Atom Co", vertical="dtc_physical")
    session.add(biz)
    await session.commit()
    biz_id = biz.id

    async def boom(*args, **kwargs):
        raise RuntimeError("simulated event_log failure")

    monkeypatch.setattr(tools_module.event_log, "write", boom)

    ctx = ToolContext(db=session, session_id=ag.id, user_id=user.id, business_id=biz_id)

    with pytest.raises(RuntimeError, match="simulated event_log failure"):
        await _request_user_approval(
            ctx,
            {
                "kind": "spend",
                "summary": "Spend $340 on TikTok creatives.",
                "business_id": str(biz_id),
                "details": {"amount_cents": 34000},
            },
        )

    await session.rollback()
    approvals = (await session.execute(select(Approval).where(Approval.business_id == biz_id))).all()
    assert approvals == [], "Approval row leaked despite event_log failure"


@requires_db
@pytest.mark.asyncio
async def test_create_business_happy_path_writes_both_atomically(session) -> None:
    user, ag = await _seed_user_and_session(session)

    ctx = ToolContext(db=session, session_id=ag.id, user_id=user.id, business_id=None)
    result = await _create_business(
        ctx,
        {"name": "Happy Co", "vertical": "dtc_physical", "weekly_spend_cap_cents": 50000},
    )
    assert result["status"] == "ok"
    biz_id_str = result["business_id"]

    rows = (
        await session.execute(select(Business).where(Business.id == uuid.UUID(biz_id_str)))
    ).all()
    assert len(rows) == 1

    events = (
        await session.execute(
            select(AgentEvent).where(
                AgentEvent.business_id == uuid.UUID(biz_id_str),
                AgentEvent.event_type == "business_created",
            )
        )
    ).all()
    assert len(events) == 1

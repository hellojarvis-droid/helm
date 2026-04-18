"""request_spend CEO tool — intent logging + validation."""

from __future__ import annotations

import time
import uuid

import pytest
from helm.agents.tools import ToolContext, _request_spend
from helm.db.models import AgentEvent, AgentSession, Business, User
from helm.services import kill_switch
from sqlalchemy import select

from tests.conftest import requires_db


def _prime(user_id):
    kill_switch._cache[user_id] = kill_switch._CacheEntry(active=False, fetched_at=time.monotonic())


@requires_db
@pytest.mark.asyncio
async def test_request_spend_writes_intent_event(session) -> None:
    user = User(supabase_id="sub-rs-1", email="rs1@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="Candle", vertical="dtc_physical")
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.commit()

    _prime(user.id)

    ctx = ToolContext(
        db=session,
        session_id=ag.id,
        user_id=user.id,
        business_id=biz.id,
    )
    result = await _request_spend(
        ctx,
        {
            "business_id": str(biz.id),
            "amount_cents": 34000,
            "merchant_hint": "Meta Ads",
            "purpose": "Candle store launch 72h Meta Smart+ test",
        },
    )

    assert result["status"] == "ok"
    assert result["amount_cents"] == 34000
    assert "intent_id" in result

    rows = (
        (
            await session.execute(
                select(AgentEvent)
                .where(AgentEvent.event_type == "spend_intent")
                .where(AgentEvent.business_id == biz.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    ev = rows[0]
    assert ev.payload["amount_cents"] == 34000
    assert ev.payload["merchant_hint"] == "Meta Ads"
    assert "Candle store" in ev.payload["purpose"]


@requires_db
@pytest.mark.asyncio
async def test_request_spend_rejects_foreign_business(session) -> None:
    user_a = User(supabase_id="sub-rs-a", email="a@example.com", tier="founder")
    user_b = User(supabase_id="sub-rs-b", email="b@example.com", tier="founder")
    session.add_all([user_a, user_b])
    await session.flush()
    biz_a = Business(user_id=user_a.id, name="A's", vertical="dtc_physical")
    session.add(biz_a)
    await session.flush()
    ag = AgentSession(user_id=user_b.id, business_id=None, status="active")
    session.add(ag)
    await session.commit()

    ctx = ToolContext(
        db=session,
        session_id=ag.id,
        user_id=user_b.id,  # user B calls from their session
        business_id=None,
    )
    # ...trying to spend on user A's business.
    result = await _request_spend(
        ctx,
        {
            "business_id": str(biz_a.id),
            "amount_cents": 5000,
            "merchant_hint": "Meta Ads",
            "purpose": "try to spend on someone else's business",
        },
    )
    assert result["status"] == "error"
    assert "not found" in result["summary"]


@requires_db
@pytest.mark.asyncio
async def test_request_spend_validates_arguments(session) -> None:
    user = User(supabase_id="sub-rs-v", email="v@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="X", vertical="dtc_physical")
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.commit()

    ctx = ToolContext(db=session, session_id=ag.id, user_id=user.id, business_id=biz.id)

    # Missing business_id.
    r1 = await _request_spend(ctx, {"amount_cents": 100, "merchant_hint": "m", "purpose": "p"})
    assert r1["status"] == "error"
    # Malformed business_id.
    r2 = await _request_spend(
        ctx,
        {"business_id": "not-a-uuid", "amount_cents": 100, "merchant_hint": "m", "purpose": "p"},
    )
    assert r2["status"] == "error"
    # Non-positive amount.
    r3 = await _request_spend(
        ctx,
        {
            "business_id": str(biz.id),
            "amount_cents": 0,
            "merchant_hint": "m",
            "purpose": "p",
        },
    )
    assert r3["status"] == "error"
    # Empty merchant / purpose.
    r4 = await _request_spend(
        ctx,
        {
            "business_id": str(biz.id),
            "amount_cents": 100,
            "merchant_hint": "",
            "purpose": "p",
        },
    )
    assert r4["status"] == "error"
    _ = uuid.UUID  # silence unused import on some paths

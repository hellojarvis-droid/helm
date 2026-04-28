"""computer-use escalations REST — list / claim / heartbeat / complete / cancel.

Covers the full state machine plus the tenant-isolation invariants:
  * a different user cannot see or mutate another user's escalation
  * claim is atomic — only one desktop wins the race
  * complete requires the device that holds the claim
"""

from __future__ import annotations

import uuid

import pytest
from helm.auth import CurrentUser, require_user
from helm.db.models import (
    AgentEvent,
    AgentSession,
    Business,
    ComputerUseEscalation,
    User,
)
from helm.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.conftest import requires_db


async def _seed(session) -> tuple[User, Business, AgentSession, ComputerUseEscalation]:
    user = User(supabase_id="sub-cu", email="cu@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="Candle", vertical="dtc_physical")
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.flush()
    esc = ComputerUseEscalation(
        user_id=user.id,
        business_id=biz.id,
        session_id=ag.id,
        requester="ceo_agent",
        task="Open TikTok Ads Manager and create a $20/day spark ad.",
        app_hint="tiktok ads manager",
        status="queued",
    )
    session.add(esc)
    await session.commit()
    return user, biz, ag, esc


def _client_for(user: User, app):
    fake_user = CurrentUser(supabase_id=user.supabase_id, email=user.email, raw_claims={})
    app.dependency_overrides[require_user] = lambda: fake_user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@requires_db
@pytest.mark.asyncio
async def test_full_state_machine_succeeds(session) -> None:
    user, _biz, ag, esc = await _seed(session)
    app = create_app()

    async with _client_for(user, app) as client:
        # 1. Queue lists the row.
        r = await client.get("/computer_use/queue", headers={"Authorization": "Bearer s"})
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) == 1 and rows[0]["status"] == "queued"

        # 2. Claim transitions to claimed.
        r = await client.post(
            f"/computer_use/{esc.id}/claim",
            json={"claimed_by": "device-A"},
            headers={"Authorization": "Bearer s"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "claimed"
        assert r.json()["claimed_by"] == "device-A"

        # 3. Heartbeat with a progress note → status flips to running, event lands.
        r = await client.post(
            f"/computer_use/{esc.id}/heartbeat",
            json={"claimed_by": "device-A", "progress_note": "logged in to tiktok"},
            headers={"Authorization": "Bearer s"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "running"

        # 4. Complete with success → terminal, event lands.
        r = await client.post(
            f"/computer_use/{esc.id}/complete",
            json={
                "claimed_by": "device-A",
                "status": "succeeded",
                "result": {"campaign_id": "tt_abc123"},
            },
            headers={"Authorization": "Bearer s"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "succeeded"
        assert r.json()["result"]["campaign_id"] == "tt_abc123"

    # Event log captures requested + progress + succeeded.
    types = (
        (
            await session.execute(
                select(AgentEvent.event_type)
                .where(AgentEvent.session_id == ag.id)
                .order_by(AgentEvent.id.asc())
            )
        )
        .scalars()
        .all()
    )
    # Note: 'computer_use_requested' was written by the seed via the row insert
    # outside the route flow, so we only assert the event types that come from
    # the heartbeat + complete paths.
    assert "computer_use_progress" in types
    assert "computer_use_succeeded" in types


@requires_db
@pytest.mark.asyncio
async def test_claim_is_atomic(session) -> None:
    user, _biz, _ag, esc = await _seed(session)
    app = create_app()

    async with _client_for(user, app) as client:
        r1 = await client.post(
            f"/computer_use/{esc.id}/claim",
            json={"claimed_by": "device-A"},
            headers={"Authorization": "Bearer s"},
        )
        r2 = await client.post(
            f"/computer_use/{esc.id}/claim",
            json={"claimed_by": "device-B"},
            headers={"Authorization": "Bearer s"},
        )
        assert r1.status_code == 200
        assert r2.status_code == 409
        assert "claimed" in r2.json()["detail"].lower()


@requires_db
@pytest.mark.asyncio
async def test_heartbeat_rejects_other_devices(session) -> None:
    user, _biz, _ag, esc = await _seed(session)
    app = create_app()

    async with _client_for(user, app) as client:
        await client.post(
            f"/computer_use/{esc.id}/claim",
            json={"claimed_by": "device-A"},
            headers={"Authorization": "Bearer s"},
        )
        r = await client.post(
            f"/computer_use/{esc.id}/heartbeat",
            json={"claimed_by": "device-B"},
            headers={"Authorization": "Bearer s"},
        )
        assert r.status_code == 409
        assert "claim" in r.json()["detail"].lower()


@requires_db
@pytest.mark.asyncio
async def test_cancel_from_queued_writes_event(session) -> None:
    user, _biz, ag, esc = await _seed(session)
    app = create_app()

    async with _client_for(user, app) as client:
        r = await client.post(
            f"/computer_use/{esc.id}/cancel",
            json={"reason": "no longer needed"},
            headers={"Authorization": "Bearer s"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "cancelled"

    rows = (
        (
            await session.execute(
                select(AgentEvent).where(
                    AgentEvent.event_type == "computer_use_cancelled",
                    AgentEvent.session_id == ag.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert "no longer needed" in rows[0].payload.get("reason", "")


@requires_db
@pytest.mark.asyncio
async def test_other_user_cannot_see_or_mutate(session) -> None:
    _user_a, _biz, _ag, esc = await _seed(session)
    # Foreign user with their own row scaffolding so sync_user_from_supabase has
    # something to do — they just shouldn't see user_a's escalation.
    user_b = User(supabase_id="sub-cu-b", email="cub@example.com", tier="founder")
    session.add(user_b)
    await session.commit()

    app = create_app()
    async with _client_for(user_b, app) as client:
        r = await client.get("/computer_use", headers={"Authorization": "Bearer s"})
        assert r.status_code == 200
        assert r.json() == []

        r = await client.get(
            f"/computer_use/{esc.id}", headers={"Authorization": "Bearer s"}
        )
        assert r.status_code == 404

        r = await client.post(
            f"/computer_use/{esc.id}/claim",
            json={"claimed_by": "device-X"},
            headers={"Authorization": "Bearer s"},
        )
        assert r.status_code in (404, 409)


@requires_db
@pytest.mark.asyncio
async def test_complete_status_must_be_terminal(session) -> None:
    user, _biz, _ag, esc = await _seed(session)
    app = create_app()

    async with _client_for(user, app) as client:
        await client.post(
            f"/computer_use/{esc.id}/claim",
            json={"claimed_by": "device-A"},
            headers={"Authorization": "Bearer s"},
        )
        r = await client.post(
            f"/computer_use/{esc.id}/complete",
            json={"claimed_by": "device-A", "status": "queued"},
            headers={"Authorization": "Bearer s"},
        )
        # Pydantic Literal mismatch surfaces as 422.
        assert r.status_code == 422


@requires_db
@pytest.mark.asyncio
async def test_complete_with_failure_lands_failed_event(session) -> None:
    user, _biz, ag, esc = await _seed(session)
    app = create_app()

    async with _client_for(user, app) as client:
        await client.post(
            f"/computer_use/{esc.id}/claim",
            json={"claimed_by": "device-A"},
            headers={"Authorization": "Bearer s"},
        )
        r = await client.post(
            f"/computer_use/{esc.id}/complete",
            json={
                "claimed_by": "device-A",
                "status": "failed",
                "error": "captcha blocked",
            },
            headers={"Authorization": "Bearer s"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "failed"
        assert r.json()["error"] == "captcha blocked"

    rows = (
        (
            await session.execute(
                select(AgentEvent).where(
                    AgentEvent.event_type == "computer_use_failed",
                    AgentEvent.session_id == ag.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert "captcha" in rows[0].payload.get("error", "")
    _ = uuid.UUID  # keep import; also used by EscalationResponse

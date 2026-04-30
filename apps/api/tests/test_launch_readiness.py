"""Launch workflow readiness gates for the hand-off approval."""

from __future__ import annotations

import pytest
from helm.db.models import AgentSession, Approval, Business, BusinessLaunch, LaunchStep, User
from helm.services.launch_workflow import STEPS, _run_first_approval
from sqlalchemy import select

from tests.conftest import requires_db


async def _seed_launch(session, *, storefront_status: str, ad_status: str):
    user = User(supabase_id="sub-launch-ready", email="launch@example.com", tier="founder")
    session.add(user)
    await session.flush()
    biz = Business(
        user_id=user.id,
        name="Candle Launch",
        vertical="dtc_physical",
        weekly_spend_cap_cents=50_000,
    )
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.flush()
    launch = BusinessLaunch(
        business_id=biz.id,
        session_id=ag.id,
        status="running",
        current_step="first_approval",
    )
    session.add(launch)
    await session.flush()
    for order, step in enumerate(STEPS):
        status = "completed"
        output = {}
        if step == "storefront":
            status = storefront_status
            output = (
                {"summary": "Storefront live", "store_url": "https://example.myshopify.com"}
                if storefront_status == "completed"
                else {"reason": "shopify_not_connected"}
            )
        elif step == "ad_accounts":
            status = ad_status
            output = (
                {"channels_checked": ["meta_ads"], "summary": "Meta Ads ready"}
                if ad_status == "completed"
                else {"reason": "no_ad_platforms_connected"}
            )
        elif step == "first_approval":
            status = "pending"
        session.add(
            LaunchStep(
                launch_id=launch.id,
                step_name=step,
                step_order=order,
                status=status,
                output=output,
            )
        )
    await session.commit()
    return biz, launch


@requires_db
@pytest.mark.asyncio
async def test_first_approval_skips_until_storefront_and_ads_are_ready(session) -> None:
    biz, launch = await _seed_launch(
        session,
        storefront_status="skipped",
        ad_status="skipped",
    )

    result = await _run_first_approval(session, launch, biz)

    assert result["__skipped__"] is True
    assert result["reason"] == "launch_not_ready"
    checks = {check["key"]: check for check in result["readiness"]["checks"]}
    assert checks["storefront"]["status"] == "blocked"
    assert checks["ad_accounts"]["status"] == "blocked"

    approvals = (
        (await session.execute(select(Approval).where(Approval.business_id == biz.id)))
        .scalars()
        .all()
    )
    assert approvals == []


@requires_db
@pytest.mark.asyncio
async def test_first_approval_created_when_launch_is_ready(session) -> None:
    biz, launch = await _seed_launch(
        session,
        storefront_status="completed",
        ad_status="completed",
    )

    result = await _run_first_approval(session, launch, biz)

    assert "approval_id" in result
    assert result["readiness"]["ready"] is True
    assert result["amount_cents"] == 30_000

    approvals = (
        (await session.execute(select(Approval).where(Approval.business_id == biz.id)))
        .scalars()
        .all()
    )
    assert len(approvals) == 1
    assert approvals[0].details["readiness"]["ready"] is True

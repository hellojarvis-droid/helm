"""Business launch orchestrator — Phase 3's staged workflow.

A business launch is a pipeline of named steps. Each step is idempotent,
independently observable via `agent_events`, and recovers on restart by
reading the last completed step in the `launch_steps` table.

Design invariants:

  1. **Durable.** State lives in Postgres (`business_launches` +
     `launch_steps`). If the API process restarts mid-launch, `resume`
     picks up from the first pending step and continues.

  2. **Idempotent per step.** Each step checks its own preconditions
     (does the Stripe account already exist? is the brand kit already
     populated?) before acting. Re-running a completed step is a no-op.

  3. **Kill-switch-aware.** Before every step and every LLM call, we
     assert the kill switch is off. Flipping it mid-launch halts the
     next step, marks the launch `cancelled`, and leaves prior steps
     intact so the user can audit what ran.

  4. **Graceful degradation.** Steps that need an external toolkit the
     user hasn't connected (Shopify, Meta Ads, Printful) mark themselves
     `skipped` with a human-readable reason. The hand-off approval is
     gated by a readiness checklist so Helm does not ask for paid spend
     when the storefront or ad channel setup is missing.

  5. **Event-sourced.** Every transition writes an `agent_events` row
     so SSE can stream the launch theater without polling DB state.

The steps, in order:

  stripe_connect      — create Stripe Connect Custom account
  issuing_card        — create cardholder + virtual card with spending_controls
  brand_kit           — Creative Director produces the brand identity
  storefront          — Product Builder stands up Shopify + domain + products
  ad_accounts         — Ads Operator verifies/creates Meta/Google/TikTok
  first_approval      — request first-week ad-spend approval to hand over
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import helm.agents.specialists.registry  # noqa: F401 — ensure specialists registered
from helm.agents.specialists import base as specialists
from helm.config import get_settings
from helm.db.models import (
    AgentSession,
    Approval,
    Business,
    BusinessLaunch,
    Integration,
    LaunchStep,
)
from helm.db.session import session_scope
from helm.services import event_log, kill_switch, stripe_client

log = structlog.get_logger("helm.launch_workflow")

# Step ordering. Changing this order is a schema migration — runs in progress
# key off step_order to decide resumption, so renumbering mid-flight would
# skip or repeat steps.
STEPS: tuple[str, ...] = (
    "stripe_connect",
    "issuing_card",
    "brand_kit",
    "storefront",
    "ad_accounts",
    "first_approval",
)


# ────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class LaunchSnapshot:
    """Point-in-time view of a launch + all its steps."""

    launch_id: uuid.UUID
    business_id: uuid.UUID
    status: str
    current_step: str | None
    started_at: datetime
    completed_at: datetime | None
    error: str | None
    steps: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "launch_id": str(self.launch_id),
            "business_id": str(self.business_id),
            "status": self.status,
            "current_step": self.current_step,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "steps": self.steps,
        }


class LaunchAlreadyActiveError(Exception):
    """Raised when start_launch is called on a business already launching."""

    def __init__(self, launch_id: uuid.UUID) -> None:
        super().__init__(f"launch {launch_id} is already active for this business")
        self.launch_id = launch_id


# Historical alias preserved for any in-flight callers — the PEP-8 name is
# the one to use.
LaunchAlreadyActive = LaunchAlreadyActiveError


async def start_launch(
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    user_id: uuid.UUID,
    session_id: uuid.UUID | None = None,
) -> BusinessLaunch:
    """Create a new launch row + pending steps. Raises if an active launch
    already exists for this business (partial unique index catches the race).

    Does NOT run the launch — caller schedules that via `schedule_launch`.
    """
    existing = (
        (
            await db.execute(
                select(BusinessLaunch).where(
                    BusinessLaunch.business_id == business_id,
                    BusinessLaunch.status.in_(("pending", "running")),
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        raise LaunchAlreadyActive(existing.id)

    launch = BusinessLaunch(
        business_id=business_id,
        status="pending",
        current_step=STEPS[0],
        session_id=session_id,
    )
    db.add(launch)
    await db.flush()
    for i, name in enumerate(STEPS):
        db.add(LaunchStep(launch_id=launch.id, step_name=name, step_order=i, status="pending"))

    if session_id is not None:
        await event_log.write(
            db,
            session_id=session_id,
            business_id=business_id,
            event_type="launch_started",
            agent_name="launch_workflow",
            payload={"launch_id": str(launch.id), "steps": list(STEPS)},
        )

    await db.commit()
    await db.refresh(launch)
    log.info(
        "launch.created", launch_id=str(launch.id), business_id=str(business_id), steps=len(STEPS)
    )
    return launch


# In-process task registry so the FastAPI lifespan can see + cancel running
# launches. Holds references so GC doesn't cancel background tasks.
_running: dict[uuid.UUID, asyncio.Task[None]] = {}


def schedule_launch(launch_id: uuid.UUID) -> asyncio.Task[None]:
    """Fire-and-forget: kick off `run_launch` in the background.

    Idempotent — a second schedule call for the same launch_id while the
    first is running returns the same task.
    """
    existing = _running.get(launch_id)
    if existing is not None and not existing.done():
        return existing
    task = asyncio.create_task(_safe_run_launch(launch_id))
    _running[launch_id] = task
    task.add_done_callback(lambda _t: _running.pop(launch_id, None))
    return task


async def resume_pending_launches() -> int:
    """Called from the FastAPI lifespan on startup — finds any launches left
    in `pending`/`running` from a previous process and re-schedules them.
    Returns the count scheduled.
    """
    async with session_scope() as db:
        rows = (
            (
                await db.execute(
                    select(BusinessLaunch).where(BusinessLaunch.status.in_(("pending", "running")))
                )
            )
            .scalars()
            .all()
        )
        for launch in rows:
            schedule_launch(launch.id)
        if rows:
            log.info("launch.resumed_count", count=len(rows))
        return len(rows)


async def snapshot(db: AsyncSession, launch_id: uuid.UUID) -> LaunchSnapshot | None:
    """Snapshot a launch + all its steps. Returns None if the launch is unknown."""
    launch = await db.get(BusinessLaunch, launch_id)
    if launch is None:
        return None
    steps_q = await db.execute(
        select(LaunchStep).where(LaunchStep.launch_id == launch_id).order_by(LaunchStep.step_order)
    )
    steps = [_step_to_dict(s) for s in steps_q.scalars().all()]
    return LaunchSnapshot(
        launch_id=launch.id,
        business_id=launch.business_id,
        status=launch.status,
        current_step=launch.current_step,
        started_at=launch.started_at,
        completed_at=launch.completed_at,
        error=launch.error,
        steps=steps,
    )


async def snapshot_for_business(db: AsyncSession, business_id: uuid.UUID) -> LaunchSnapshot | None:
    """Return the latest launch for a business (active or most recent)."""
    q = (
        select(BusinessLaunch)
        .where(BusinessLaunch.business_id == business_id)
        .order_by(BusinessLaunch.started_at.desc())
        .limit(1)
    )
    launch = (await db.execute(q)).scalar_one_or_none()
    if launch is None:
        return None
    return await snapshot(db, launch.id)


# ────────────────────────────────────────────────────────────────────
# The driver
# ────────────────────────────────────────────────────────────────────


async def _safe_run_launch(launch_id: uuid.UUID) -> None:
    try:
        await run_launch(launch_id)
    except Exception:  # never let an unhandled error kill the worker task
        log.exception("launch.crash", launch_id=str(launch_id))
        async with session_scope() as db:
            await _mark_failed(db, launch_id, "internal error")


async def run_launch(launch_id: uuid.UUID) -> None:
    """Main driver: walk pending steps in order and run each. Safe to call
    multiple times — already-completed steps are skipped.

    Opens a fresh DB session per step so transactions are narrow and failures
    don't poison the whole launch.
    """
    # Mark launch running in its own transaction so the UI sees the transition
    # immediately even before the first step completes.
    async with session_scope() as db:
        launch = await db.get(BusinessLaunch, launch_id)
        if launch is None:
            log.warning("launch.unknown_id", launch_id=str(launch_id))
            return
        if launch.status in ("completed", "failed", "cancelled"):
            return  # already terminal
        business = await db.get(Business, launch.business_id)
        if business is None:
            launch.status = "failed"
            launch.error = "business_deleted"
            launch.completed_at = datetime.now(UTC)
            await db.commit()
            return
        launch.status = "running"
        await db.commit()

    # Pull the ordered step list once. Each step runs in its own session.
    async with session_scope() as db:
        steps_q = await db.execute(
            select(LaunchStep)
            .where(LaunchStep.launch_id == launch_id)
            .order_by(LaunchStep.step_order)
        )
        ordered_steps = list(steps_q.scalars().all())

    for step in ordered_steps:
        if step.status in ("completed", "skipped"):
            continue

        # Kill-switch check before each step.
        async with session_scope() as db:
            launch = await db.get(BusinessLaunch, launch_id)
            if launch is None:
                return
            business = await db.get(Business, launch.business_id)
            if business is None:
                await _mark_failed(db, launch_id, "business_deleted")
                return
            try:
                await kill_switch.assert_not_set(db, business.user_id)
            except kill_switch.KillSwitchActivated:
                launch.status = "cancelled"
                launch.error = "kill_switch_activated"
                launch.completed_at = datetime.now(UTC)
                await db.commit()
                log.info("launch.cancelled_by_kill_switch", launch_id=str(launch_id))
                return

        # Run the step with its own session so we can commit the result
        # atomically and advance the cursor.
        await _run_one_step(launch_id, step.step_name)

    # All steps done — mark completed.
    async with session_scope() as db:
        launch = await db.get(BusinessLaunch, launch_id)
        if launch is None:
            return
        # Did any step fail? If so, mark launch failed but keep completed_at.
        fail_q = await db.execute(
            select(LaunchStep).where(
                LaunchStep.launch_id == launch_id, LaunchStep.status == "failed"
            )
        )
        had_failure = fail_q.first() is not None
        launch.status = "failed" if had_failure else "completed"
        launch.current_step = None
        launch.completed_at = datetime.now(UTC)
        if had_failure and not launch.error:
            launch.error = "one_or_more_steps_failed"
        await db.commit()

        if launch.session_id is not None:
            async with session_scope() as db2:
                await event_log.write(
                    db2,
                    session_id=launch.session_id,
                    business_id=launch.business_id,
                    event_type="launch_completed" if not had_failure else "launch_failed",
                    agent_name="launch_workflow",
                    payload={"launch_id": str(launch_id)},
                )
    log.info("launch.done", launch_id=str(launch_id))


async def _run_one_step(launch_id: uuid.UUID, step_name: str) -> None:
    """Open a session, mark step running, dispatch to the runner, write the
    result. Exceptions are caught + recorded as step failures so the driver
    can continue or terminate cleanly."""
    async with session_scope() as db:
        step_q = await db.execute(
            select(LaunchStep).where(
                LaunchStep.launch_id == launch_id, LaunchStep.step_name == step_name
            )
        )
        step = step_q.scalar_one_or_none()
        if step is None:
            log.warning("launch.step_missing", launch_id=str(launch_id), step=step_name)
            return
        if step.status in ("completed", "skipped"):
            return
        launch = await db.get(BusinessLaunch, launch_id)
        if launch is None:
            return
        business = await db.get(Business, launch.business_id)
        if business is None:
            return

        step.status = "running"
        step.started_at = datetime.now(UTC)
        launch.current_step = step_name
        await db.commit()

        if launch.session_id is not None:
            await event_log.write(
                db,
                session_id=launch.session_id,
                business_id=launch.business_id,
                event_type="launch_step_started",
                agent_name="launch_workflow",
                payload={"step": step_name, "launch_id": str(launch_id)},
            )
            await db.commit()

        runner = _STEP_RUNNERS.get(step_name)
        if runner is None:
            step.status = "failed"
            step.error = f"no runner registered for '{step_name}'"
            step.completed_at = datetime.now(UTC)
            await db.commit()
            return

        try:
            result = await runner(db, launch, business)
            # Runner returns either {"skipped": reason} or the output dict.
            if isinstance(result, dict) and result.get("__skipped__"):
                step.status = "skipped"
                step.output = {k: v for k, v in result.items() if k != "__skipped__"}
            else:
                step.status = "completed"
                step.output = result
        except kill_switch.KillSwitchActivated:
            step.status = "failed"
            step.error = "kill_switch_activated"
        except Exception as e:  # record and continue
            log.exception("launch.step_failed", step=step_name, launch_id=str(launch_id))
            step.status = "failed"
            step.error = str(e)[:500]
        step.completed_at = datetime.now(UTC)
        await db.commit()

        if launch.session_id is not None:
            async with session_scope() as db2:
                await event_log.write(
                    db2,
                    session_id=launch.session_id,
                    business_id=launch.business_id,
                    event_type=f"launch_step_{step.status}",
                    agent_name="launch_workflow",
                    payload={
                        "step": step_name,
                        "launch_id": str(launch_id),
                        "output": step.output,
                        "error": step.error,
                    },
                )


async def _mark_failed(db: AsyncSession, launch_id: uuid.UUID, error: str) -> None:
    launch = await db.get(BusinessLaunch, launch_id)
    if launch is None:
        return
    launch.status = "failed"
    launch.error = error
    launch.completed_at = datetime.now(UTC)
    await db.commit()


def _step_to_dict(s: LaunchStep) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "step_name": s.step_name,
        "status": s.status,
        "step_order": s.step_order,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        "output": s.output,
        "error": s.error,
    }


# ────────────────────────────────────────────────────────────────────
# Step runners
# ────────────────────────────────────────────────────────────────────


StepResult = dict[str, Any]
StepRunner = Callable[[AsyncSession, BusinessLaunch, Business], Awaitable[StepResult]]


def _skipped(reason: str) -> StepResult:
    return {"__skipped__": True, "reason": reason}


async def _run_stripe_connect(
    db: AsyncSession, launch: BusinessLaunch, business: Business
) -> StepResult:
    """Create a Stripe Connect Custom account for the business (idempotent).

    We do NOT block on user-side KYC completion — the onboarding URL is
    returned for the launch-theater UI to surface. The webhook
    `account.updated` flips `stripe_onboarding_complete` separately.
    """
    if not get_settings().stripe_secret_key:
        return _skipped("stripe_not_configured")
    if business.stripe_account_id:
        return {
            "stripe_account_id": business.stripe_account_id,
            "already_existed": True,
        }
    from helm.db.models import User

    user_row = await db.get(User, business.user_id)
    email = user_row.email if user_row else f"business+{business.id}@helm.app"
    acct_id = await stripe_client.create_connect_account(
        business_name=business.name,
        business_email=email,
    )
    business.stripe_account_id = acct_id
    await db.commit()
    return {"stripe_account_id": acct_id, "already_existed": False}


async def _run_issuing_card(
    db: AsyncSession, launch: BusinessLaunch, business: Business
) -> StepResult:
    """Create a virtual card with weekly caps + MCC allowlist (idempotent)."""
    settings = get_settings()
    if not settings.stripe_issuing_enabled:
        return _skipped("issuing_feature_flag_off")
    if not business.stripe_account_id:
        return _skipped("no_stripe_account_yet")
    if business.stripe_card_id:
        return {
            "card_id": business.stripe_card_id,
            "cardholder_id": business.stripe_issuing_cardholder_id,
            "already_existed": True,
        }
    from helm.db.models import User

    user_row = await db.get(User, business.user_id)
    email = user_row.email if user_row else f"business+{business.id}@helm.app"

    cardholder_id = (
        business.stripe_issuing_cardholder_id
        or await stripe_client.create_issuing_cardholder(
            account_id=business.stripe_account_id,
            business_name=business.name,
            business_email=email,
        )
    )
    card_id = await stripe_client.create_issuing_card(
        account_id=business.stripe_account_id,
        cardholder_id=cardholder_id,
        weekly_spend_cap_cents=business.weekly_spend_cap_cents,
        allowed_mcc_codes=business.allowed_mcc_codes,
    )
    business.stripe_issuing_cardholder_id = cardholder_id
    business.stripe_card_id = card_id
    await db.commit()
    return {
        "card_id": card_id,
        "cardholder_id": cardholder_id,
        "weekly_cap_cents": business.weekly_spend_cap_cents,
        "already_existed": False,
    }


async def _run_brand_kit(
    db: AsyncSession, launch: BusinessLaunch, business: Business
) -> StepResult:
    """Creative Director generates the brand identity (logo concept, palette,
    typography pair, voice). Idempotent — if brand_kit has a `name` field
    already, we treat it as already generated."""
    if business.brand_kit and business.brand_kit.get("name"):
        return {"already_existed": True, "summary": "brand kit already populated"}

    session_id = await _ensure_launch_session(db, launch)
    task = (
        f"Design a brand identity kit for '{business.name}', a {business.vertical} business. "
        "Return a single JSON object with: name (keep the business name), tagline, "
        "brand_voice (one paragraph), palette (primary, secondary, accent, neutral — "
        "6-char hex codes), typography (display, body — Google-Fonts-available names), "
        "moodboard_keywords (list of 4-6). Keep it tight and on-brand; no commentary."
    )
    result = await specialists.invoke(
        db=db,
        session_id=session_id,
        specialist_name="creative_director",
        task=task,
        user_id=business.user_id,
        business_id=business.id,
    )
    # creative_director is an LLMSpecialist with a JSON-shaped prompt — but
    # we don't hard-depend on the parse succeeding. Store whatever came back
    # + attempt a JSON extraction for the structured fields.
    parsed = _extract_json_object(result.summary)
    merged = dict(business.brand_kit or {})
    if parsed:
        merged.update(parsed)
    merged["_summary"] = result.summary[:2000]
    merged["_generated_at"] = datetime.now(UTC).isoformat()
    business.brand_kit = merged
    await db.commit()
    return {
        "fields_populated": sorted(parsed.keys()) if parsed else [],
        "cost_cents": result.cost_cents,
        "specialist_status": result.status,
    }


async def _run_storefront(
    db: AsyncSession, launch: BusinessLaunch, business: Business
) -> StepResult:
    """Product Builder stands up the Shopify store. Requires Shopify Composio
    integration — skipped cleanly if not connected."""
    # Check connected toolkits — Product Builder needs at least shopify.
    integ_q = await db.execute(
        select(Integration.toolkit).where(
            Integration.business_id == business.id,
            Integration.status == "active",
        )
    )
    connected = set(integ_q.scalars().all())
    if "shopify" not in connected:
        return _skipped("shopify_not_connected")

    session_id = await _ensure_launch_session(db, launch)
    vertical_guide = _vertical_guidance(business.vertical)
    task = (
        f"Stand up a Shopify storefront for '{business.name}' ({business.vertical}). "
        f"Brand context: {_brand_summary(business.brand_kit)}. "
        f"{vertical_guide} "
        "Produce: a ready-to-review store URL, 5-10 products with titles + descriptions, "
        "a working Dawn-themed storefront on mobile, policies loaded, Stripe connected. "
        "Summarize what you did, what's live, and anything you couldn't automate."
    )
    result = await specialists.invoke(
        db=db,
        session_id=session_id,
        specialist_name="product_builder",
        task=task,
        user_id=business.user_id,
        business_id=business.id,
    )
    return {
        "status": result.status,
        "summary": result.summary[:2000],
        "cost_cents": result.cost_cents,
    }


async def _run_ad_accounts(
    db: AsyncSession, launch: BusinessLaunch, business: Business
) -> StepResult:
    """Ads Operator verifies/creates Meta/Google/TikTok ad accounts.
    Skipped if none of those toolkits are connected."""
    integ_q = await db.execute(
        select(Integration.toolkit).where(
            Integration.business_id == business.id,
            Integration.status == "active",
        )
    )
    connected = set(integ_q.scalars().all())
    channels = sorted(connected.intersection({"meta_ads", "google_ads", "tiktok_ads"}))
    if not channels:
        return _skipped("no_ad_platforms_connected")

    session_id = await _ensure_launch_session(db, launch)
    task = (
        f"Verify the business '{business.name}' has functioning ad accounts on: "
        f"{', '.join(channels)}. For each channel, confirm an ad account exists, the "
        "business is verified where required, and the tracking pixel is set up on the "
        "storefront. Do NOT launch any campaign — that needs user approval. Report what "
        "you found per channel."
    )
    result = await specialists.invoke(
        db=db,
        session_id=session_id,
        specialist_name="ads_operator",
        task=task,
        user_id=business.user_id,
        business_id=business.id,
    )
    return {
        "channels_checked": channels,
        "summary": result.summary[:2000],
        "cost_cents": result.cost_cents,
    }


async def _run_first_approval(
    db: AsyncSession, launch: BusinessLaunch, business: Business
) -> StepResult:
    """Create the hand-off approval card: the first ad spend budget request.

    This is the moment PRD §4.1 describes: "Approve $300 for first-week Meta ads?"
    It is only created once the launch is actually ready to spend; otherwise
    the step returns a checklist the UI can use as the Launch Readiness Wizard.
    """
    readiness = await _launch_readiness(db, launch)
    if not readiness["ready"]:
        return {
            "__skipped__": True,
            "reason": "launch_not_ready",
            "readiness": readiness,
            "business_status": business.status,
        }

    proposed_cents = min(30000, business.weekly_spend_cap_cents)
    approval = Approval(
        business_id=business.id,
        kind="spend",
        summary=(
            f"First-week ad-spend budget for {business.name}. Ads Operator proposes "
            f"${proposed_cents // 100} to launch the initial paid test campaign after your "
            "storefront is live."
        ),
        details={
            "amount_cents": proposed_cents,
            "merchant_hint": "Meta Ads / Google Ads",
            "purpose": (
                "Launch the first-week paid test: ~3 creative variants, $10-40/day split "
                "across Meta + Google, 72h ROAS gate, auto-pause below ROAS 1.0."
            ),
            "launch_id": str(launch.id),
            "proposed_channels": ["meta_ads", "google_ads"],
            "readiness": readiness,
        },
        expires_at=datetime.now(UTC) + timedelta(hours=72),
    )
    db.add(approval)
    await db.flush()

    session_id = await _ensure_launch_session(db, launch)
    await event_log.write(
        db,
        session_id=session_id,
        business_id=business.id,
        event_type="approval_requested",
        agent_name="launch_workflow",
        payload={
            "approval_id": str(approval.id),
            "kind": "spend",
            "amount_cents": proposed_cents,
            "summary": approval.summary,
            "details": approval.details,
            "business_id": str(business.id),
            "expires_at": approval.expires_at.isoformat(),
            "readiness": readiness,
        },
    )

    # Flip the business from initializing → active once the hand-off card exists.
    if business.status == "initializing":
        business.status = "active"
    await db.commit()
    return {
        "approval_id": str(approval.id),
        "amount_cents": proposed_cents,
        "business_status": business.status,
        "readiness": readiness,
    }


_STEP_RUNNERS: dict[str, StepRunner] = {
    "stripe_connect": _run_stripe_connect,
    "issuing_card": _run_issuing_card,
    "brand_kit": _run_brand_kit,
    "storefront": _run_storefront,
    "ad_accounts": _run_ad_accounts,
    "first_approval": _run_first_approval,
}


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


async def _ensure_launch_session(db: AsyncSession, launch: BusinessLaunch) -> uuid.UUID:
    """Return the session_id to write events against. Creates one if the
    launch was started without one (e.g., via CLI seed script)."""
    if launch.session_id is not None:
        return launch.session_id
    biz = await db.get(Business, launch.business_id)
    assert biz is not None
    sess = AgentSession(user_id=biz.user_id, business_id=launch.business_id)
    db.add(sess)
    await db.flush()
    launch.session_id = sess.id
    await db.commit()
    return sess.id


def _brand_summary(brand_kit: dict[str, Any] | None) -> str:
    if not brand_kit:
        return "no brand kit yet"
    parts: list[str] = []
    if brand_kit.get("tagline"):
        parts.append(f"tagline '{brand_kit['tagline']}'")
    palette = brand_kit.get("palette")
    if isinstance(palette, dict) and palette:
        parts.append("palette " + ", ".join(f"{k}={v}" for k, v in list(palette.items())[:3]))
    typ = brand_kit.get("typography")
    if isinstance(typ, dict):
        display = typ.get("display")
        body = typ.get("body")
        if display or body:
            parts.append(f"typography {display}/{body}")
    if not parts:
        return "brand kit generated"
    return "; ".join(parts)


def _vertical_guidance(vertical: str) -> str:
    return {
        "dtc_physical": "Use Printful or a comparable POD/inventory supplier. US shipping only.",
        "dtc_pod": "Use Printful. 5-10 POD products, US shipping.",
        "saas": "Single landing page + Stripe-hosted pricing, no inventory.",
        "services": "Landing page + scheduling (Cal.com) + Stripe checkout.",
    }.get(vertical, "Use reasonable defaults for the vertical.")


def _extract_json_object(text: str) -> dict[str, Any]:
    """Best-effort: pull the first `{...}` JSON object out of an LLM response.
    Returns {} if nothing parseable was found — callers treat empty as 'no
    structured fields' rather than an error."""
    import json

    # Fast path — the whole thing is JSON.
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    # Otherwise, scan for the first balanced `{` … `}`.
    start = text.find("{")
    if start < 0:
        return {}
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start : i + 1])
                    return obj if isinstance(obj, dict) else {}
                except Exception:
                    return {}
    return {}


async def _launch_readiness(db: AsyncSession, launch: BusinessLaunch) -> dict[str, Any]:
    rows = (
        (await db.execute(select(LaunchStep).where(LaunchStep.launch_id == launch.id)))
        .scalars()
        .all()
    )
    by_name = {step.step_name: step for step in rows}

    storefront = by_name.get("storefront")
    ad_accounts = by_name.get("ad_accounts")
    checks = [
        _readiness_check(
            key="storefront",
            label="Storefront is live",
            step=storefront,
            blocked_reason="Connect Shopify or finish the storefront before approving paid traffic.",
        ),
        _readiness_check(
            key="ad_accounts",
            label="At least one ad account is ready",
            step=ad_accounts,
            blocked_reason="Connect Meta, Google, or TikTok Ads before approving first-week spend.",
            require_channels=True,
        ),
    ]
    return {
        "ready": all(check["status"] == "ready" for check in checks),
        "checks": checks,
    }


def _readiness_check(
    *,
    key: str,
    label: str,
    step: LaunchStep | None,
    blocked_reason: str,
    require_channels: bool = False,
) -> dict[str, Any]:
    if step is None:
        return {
            "key": key,
            "label": label,
            "status": "blocked",
            "reason": "step_missing",
            "message": blocked_reason,
        }

    output = dict(step.output or {})
    if step.status != "completed":
        return {
            "key": key,
            "label": label,
            "status": "blocked",
            "reason": output.get("reason") or step.error or step.status,
            "message": blocked_reason,
        }

    if require_channels:
        channels = output.get("channels_checked")
        if not isinstance(channels, list) or not channels:
            return {
                "key": key,
                "label": label,
                "status": "blocked",
                "reason": "no_ad_channels_ready",
                "message": blocked_reason,
            }

    return {
        "key": key,
        "label": label,
        "status": "ready",
        "summary": _compact_step_summary(output),
    }


def _compact_step_summary(output: dict[str, Any]) -> str:
    for key in ("summary", "store_url"):
        value = output.get(key)
        if isinstance(value, str) and value.strip():
            return value[:240]
    channels = output.get("channels_checked")
    if isinstance(channels, list) and channels:
        return ", ".join(str(channel) for channel in channels[:4])
    return "Ready"


# Iterable helper used by the resume path — kept here so the module is
# self-contained and import order stays trivial.
def _running_launches() -> Iterable[uuid.UUID]:
    return list(_running.keys())

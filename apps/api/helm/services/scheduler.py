"""In-process cron for agent-driven jobs.

Phase 5 calls for daily ads optimization, weekly Sunday Growth-Analyst
reviews, 2-minute Social-Engagement polling, and daily Finance reconciliation.
Rather than stand up Temporal for these (which adds ops burden the Render
deployment doesn't have yet), we run an async tick loop inside the API
process.

Guarantees:

  * **Idempotent across restarts.** Each job has a row in `scheduled_jobs`
    with `last_run_at`. A job's `run_if_due` checks the watermark before
    acting and bumps it atomically. Two API workers racing on the same
    job pick exactly one winner via `SELECT … FOR UPDATE SKIP LOCKED`.

  * **Non-blocking.** The tick loop runs as one asyncio.Task started in
    the lifespan; each job iteration opens its own DB session. A slow job
    doesn't freeze the API.

  * **Failure-tolerant.** Any exception inside a job is caught, logged,
    and the job's row records `last_error` + `last_status='failed'`. The
    loop keeps ticking.

The API lifespan calls `start()` on startup and `stop()` on shutdown.
Nothing runs when `HELM_SCHEDULER_ENABLED=false` (default true in prod,
off under pytest so tests don't spawn background work).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import helm.agents.specialists.registry  # noqa: F401
from helm.agents.specialists import base as specialists
from helm.config import get_settings
from helm.db.models import AgentSession, Business, Integration, ScheduledJob
from helm.db.session import session_scope
from helm.services import event_log, kill_switch

log = structlog.get_logger("helm.scheduler")

JobFn = Callable[[AsyncSession], Awaitable[dict[str, int | str]]]


@dataclass(frozen=True, slots=True)
class Job:
    """A registered scheduled job.

    `cadence` is the minimum interval between runs — jobs won't fire more
    often than this even if the loop ticks faster. Jobs that take longer
    than `cadence` to run happen back-to-back (the watermark advances
    after completion, not before).
    """

    name: str
    cadence: timedelta
    run: JobFn


_jobs: dict[str, Job] = {}


def register(job: Job) -> None:
    _jobs[job.name] = job


# ────────────────────────────────────────────────────────────────────
# Supervisor loop
# ────────────────────────────────────────────────────────────────────


_loop_task: asyncio.Task[None] | None = None
_TICK_SECONDS = 60.0


async def start() -> None:
    """Kick off the tick loop. Idempotent — calling twice is harmless."""
    global _loop_task
    settings = get_settings()
    if not settings.scheduler_enabled:
        log.info("scheduler.disabled")
        return
    if _loop_task is not None and not _loop_task.done():
        return
    _loop_task = asyncio.create_task(_tick_forever())
    log.info("scheduler.started", jobs=sorted(_jobs.keys()))


async def stop() -> None:
    """Cancel the tick loop and wait for it to drain."""
    global _loop_task
    import contextlib

    if _loop_task is None:
        return
    _loop_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _loop_task
    _loop_task = None
    log.info("scheduler.stopped")


async def _tick_forever() -> None:
    # Small jitter on the first tick so multiple workers don't all fire at
    # the same moment after a rolling deploy.
    import random

    await asyncio.sleep(5 + random.random() * 10)
    while True:
        try:
            await tick_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("scheduler.tick_crash")
        await asyncio.sleep(_TICK_SECONDS)


async def tick_once() -> None:
    """Run each registered job that's due. Exposed for tests."""
    now = datetime.now(UTC)
    for job in list(_jobs.values()):
        try:
            await _run_if_due(job, now)
        except Exception:
            log.exception("scheduler.job_crash", job=job.name)


async def _run_if_due(job: Job, now: datetime) -> None:
    """Claim + run one job in its own transaction.

    Uses SELECT … FOR UPDATE SKIP LOCKED on the scheduled_jobs row so two
    API workers racing for the same job pick exactly one winner. The loser
    moves on.
    """
    async with session_scope() as db:
        # Ensure the row exists so we can lock it.
        row = await db.get(ScheduledJob, job.name)
        if row is None:
            row = ScheduledJob(name=job.name)
            db.add(row)
            try:
                await db.commit()
            except IntegrityError:  # another worker created it first
                await db.rollback()
                row = await db.get(ScheduledJob, job.name)
                assert row is not None

        # Lock the row for the window in which we decide + write.
        locked_q = await db.execute(
            select(ScheduledJob)
            .where(ScheduledJob.name == job.name)
            .with_for_update(skip_locked=True)
        )
        locked = locked_q.scalar_one_or_none()
        if locked is None:
            return  # another worker has it
        if locked.last_run_at is not None and now - locked.last_run_at < job.cadence:
            return

        started = datetime.now(UTC)
        locked.last_run_at = started
        locked.last_status = "running"
        locked.last_error = None
        locked.runs += 1
        await db.commit()

    # Run the job OUTSIDE the lock — could take minutes. Write the result
    # back in a fresh session so the row isn't held.
    status = "completed"
    error: str | None = None
    try:
        async with session_scope() as run_db:
            await job.run(run_db)
    except Exception as e:
        log.exception("scheduler.job_failed", job=job.name)
        status = "failed"
        error = str(e)[:400]

    async with session_scope() as finish_db:
        row = await finish_db.get(ScheduledJob, job.name)
        if row is not None:
            row.last_status = status
            row.last_error = error
            await finish_db.commit()
    log.info(
        "scheduler.job_done",
        job=job.name,
        status=status,
        duration_ms=int((datetime.now(UTC) - started).total_seconds() * 1000),
    )


# ────────────────────────────────────────────────────────────────────
# Concrete jobs
# ────────────────────────────────────────────────────────────────────


async def _ads_daily_optimization(db: AsyncSession) -> dict[str, int | str]:
    """Daily: ask Ads Operator to check ROAS + pacing on every active
    business that has at least one ad platform connected.

    This is the "kill losers fast, scale winners slowly" daily routine from
    AGENTS.md §5. Skipped per-business if kill switch is on or no channels.
    """
    # Find businesses with any of meta_ads/google_ads/tiktok_ads connected.
    q = (
        select(Business)
        .join(Integration, Integration.business_id == Business.id)
        .where(
            Business.status == "active",
            Integration.status == "active",
            Integration.toolkit.in_(("meta_ads", "google_ads", "tiktok_ads")),
        )
        .distinct()
    )
    businesses = list((await db.execute(q)).scalars().unique().all())
    ran = 0
    skipped = 0
    for biz in businesses:
        # Kill switch → skip this user's businesses silently.
        if await kill_switch.is_active(db, biz.user_id):
            skipped += 1
            continue
        sess = await _ensure_session(db, biz.user_id, biz.id)
        await event_log.write(
            db,
            session_id=sess.id,
            business_id=biz.id,
            event_type="scheduled_job_started",
            agent_name="ads_operator",
            payload={"job": "ads_daily_optimization"},
        )
        try:
            result = await specialists.invoke(
                db=db,
                session_id=sess.id,
                specialist_name="ads_operator",
                task=(
                    f"Daily optimization for '{biz.name}'. Pull yesterday's results per channel, "
                    "categorize each campaign (scale/hold/optimize/kill), compute budget "
                    "reallocation, apply safe changes (pause known losers; NEVER scale >20% in 24h "
                    "without user approval). Produce a one-paragraph digest for the CEO."
                ),
                user_id=biz.user_id,
                business_id=biz.id,
            )
            await event_log.write(
                db,
                session_id=sess.id,
                business_id=biz.id,
                event_type="scheduled_job_completed",
                agent_name="ads_operator",
                payload={
                    "job": "ads_daily_optimization",
                    "status": result.status,
                    "summary_preview": result.summary[:300],
                },
                cost_cents=result.cost_cents,
            )
            ran += 1
        except Exception as e:
            log.warning("ads_daily.failed", biz=str(biz.id), err=str(e)[:200])
            await event_log.write(
                db,
                session_id=sess.id,
                business_id=biz.id,
                event_type="scheduled_job_failed",
                agent_name="ads_operator",
                payload={"job": "ads_daily_optimization", "error": str(e)[:400]},
            )
    return {"businesses_ran": ran, "businesses_skipped": skipped}


async def _growth_weekly_review(db: AsyncSession) -> dict[str, int | str]:
    """Weekly: Growth Analyst writes a strategic review per active business.

    Schedules to run once every 7 days; cadence is enforced by the watermark
    so the first run after a deploy-gap catches up but subsequent runs settle
    into a weekly rhythm.
    """
    q = select(Business).where(Business.status == "active")
    businesses = list((await db.execute(q)).scalars().all())
    ran = 0
    skipped = 0
    for biz in businesses:
        if await kill_switch.is_active(db, biz.user_id):
            skipped += 1
            continue
        sess = await _ensure_session(db, biz.user_id, biz.id)
        await event_log.write(
            db,
            session_id=sess.id,
            business_id=biz.id,
            event_type="scheduled_job_started",
            agent_name="growth_analyst",
            payload={"job": "growth_weekly_review"},
        )
        try:
            result = await specialists.invoke(
                db=db,
                session_id=sess.id,
                specialist_name="growth_analyst",
                task=(
                    f"Weekly strategic review for '{biz.name}'. Produce: 1) What happened "
                    "(revenue, orders, CAC, LTV, ROAS, conversion), 2) Why it happened "
                    "(attribution, channel mix, creative, landing page), 3) What to do next "
                    "(3 concrete recommendations with expected impact + confidence), 4) What "
                    "to watch. Be specific, no vague prose."
                ),
                user_id=biz.user_id,
                business_id=biz.id,
            )
            await event_log.write(
                db,
                session_id=sess.id,
                business_id=biz.id,
                event_type="scheduled_job_completed",
                agent_name="growth_analyst",
                payload={
                    "job": "growth_weekly_review",
                    "status": result.status,
                    "summary_preview": result.summary[:500],
                },
                cost_cents=result.cost_cents,
            )
            ran += 1
        except Exception as e:
            log.warning("growth_weekly.failed", biz=str(biz.id), err=str(e)[:200])
            await event_log.write(
                db,
                session_id=sess.id,
                business_id=biz.id,
                event_type="scheduled_job_failed",
                agent_name="growth_analyst",
                payload={"job": "growth_weekly_review", "error": str(e)[:400]},
            )
    return {"businesses_ran": ran, "businesses_skipped": skipped}


async def _ensure_session(
    db: AsyncSession, user_id: uuid.UUID, business_id: uuid.UUID | None
) -> AgentSession:
    """Find-or-create a business-scoped agent session for scheduler writes."""
    existing = (
        await db.execute(
            select(AgentSession)
            .where(AgentSession.user_id == user_id, AgentSession.business_id == business_id)
            .order_by(AgentSession.last_active_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.last_active_at = datetime.now(UTC)
        return existing
    sess = AgentSession(user_id=user_id, business_id=business_id)
    db.add(sess)
    await db.flush()
    return sess


# Register the jobs at module import so `from helm.services import scheduler`
# triggers registration without the caller needing a separate init step.
register(
    Job(
        name="ads_daily_optimization",
        cadence=timedelta(hours=22),  # slightly < 24h so timezone drift doesn't skip days
        run=_ads_daily_optimization,
    )
)
register(
    Job(
        name="growth_weekly_review",
        cadence=timedelta(days=7),
        run=_growth_weekly_review,
    )
)


# Poll every in-flight render (queued / running) and advance terminal states.
# Small cadence because renders are short-lived (seconds to a couple of
# minutes) and the UI's SSE stream wants fresh fingerprints quickly.
async def _poll_renders(_db: AsyncSession) -> dict[str, int | str]:
    # Unused `_db` — the poller opens its own short-lived session per job so
    # a slow provider doesn't hold the scheduler's transaction open.
    from helm.services import render_worker

    result = await render_worker.poll_in_flight()
    return dict(result)


register(
    Job(
        name="poll_renders",
        cadence=timedelta(seconds=20),
        run=_poll_renders,
    )
)


# Post scheduler — publishes MasterCreatives to connected platforms at
# their scheduled time. Runs every 60s; real platform push happens
# through Composio adapters (Phase 12 wires the real calls).
async def _post_scheduler_tick(_db: AsyncSession) -> dict[str, int | str]:
    from helm.services import post_scheduler

    return post_scheduler.summarize(await post_scheduler.tick())


register(
    Job(
        name="post_scheduler",
        cadence=timedelta(seconds=60),
        run=_post_scheduler_tick,
    )
)


# Canvas generation — mirror RenderJob state onto Generation rows,
# commit/refund credits when terminal.
async def _generation_tick(_db: AsyncSession) -> dict[str, int | str]:
    from helm.services import generation

    result = await generation.tick()
    return dict(result)


register(
    Job(
        name="generation_sync",
        cadence=timedelta(seconds=15),
        run=_generation_tick,
    )
)

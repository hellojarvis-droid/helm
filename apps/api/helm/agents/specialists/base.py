"""Specialist framework.

A specialist is a focused sub-agent invoked by the CEO via `delegate_to_specialist`.
Session 2 scope: specialists are single-shot LLM calls with their own system prompt
and optional Anthropic-native tools (web_search). No sub-session state, no Composio
yet. That arrives in Session 3.

Contract:
  - `name` is the CEO's vocabulary for this specialist (e.g. "idea_scout").
  - `run(db, ctx, task)` returns a `SpecialistResult` — a structured envelope the
    CEO receives as tool_result content.
  - Specialists log their own `specialist_completed` event; the runtime's tool
    wrapper logs the outer tool_call / tool_result around it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import anthropic
from anthropic.types import MessageParam, ToolUnionParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.config import get_settings
from helm.db.models import AgentEvent, Business, Integration
from helm.services import event_log

# Token costs per million (keep in sync with runtime._cost_cents).
_COSTS = {
    "claude-opus-4-7": (1500, 7500),  # $15/M input, $75/M output → cents per M
    "claude-sonnet-4-6": (300, 1500),
    "claude-haiku-4-5-20251001": (80, 400),
}


@dataclass(frozen=True, slots=True)
class BusinessContext:
    """The slice of tenant + business state every specialist receives.

    Session 5 hydrates this from DB before `invoke()` runs the specialist —
    so Creative Director can refine an existing brand kit, Idea Scout can see
    past event summaries, etc. See AGENTS.md §11 for the full spec.

    Cross-business / orchestrator-level invocations leave business_id=None,
    in which case brand_kit + connected_integrations default to empty.
    """

    user_id: uuid.UUID
    business_id: uuid.UUID | None
    business_name: str = ""
    vertical: str = ""
    brand_kit: dict[str, Any] = field(default_factory=dict)
    connected_integrations: tuple[str, ...] = ()
    recent_events: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class SpecialistResult:
    """Structured envelope returned to the CEO Agent as tool_result content."""

    specialist: str
    status: Literal["ok", "not_implemented", "error"]
    summary: str
    metadata: dict[str, Any]
    cost_cents: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "specialist": self.specialist,
            "status": self.status,
            "summary": self.summary,
            "metadata": self.metadata,
            "cost_cents": self.cost_cents,
        }


class Specialist(Protocol):
    """Every specialist — real or stub — implements this."""

    name: str

    async def run(
        self,
        db: AsyncSession,
        ctx: BusinessContext,
        task: str,
    ) -> SpecialistResult: ...


# ────────────────────────────────────────────────────────────────────
# Shared implementations
# ────────────────────────────────────────────────────────────────────


_shared_client: anthropic.AsyncAnthropic | None = None


def _anthropic_client() -> anthropic.AsyncAnthropic:
    global _shared_client
    if _shared_client is None:
        _shared_client = anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    return _shared_client


def _cost_cents_for(model: str, input_tokens: int, output_tokens: int) -> int:
    rate_in, rate_out = _COSTS.get(model, (1500, 7500))
    cents = (input_tokens * rate_in + output_tokens * rate_out) / 1_000_000
    return int(cents + 0.5)


class LLMSpecialist:
    """A single-shot LLM-backed specialist.

    Subclass or instantiate with system prompt + model + tools. `run` does one
    Messages API call, extracts text, logs completion, returns structured envelope.
    """

    def __init__(
        self,
        *,
        name: str,
        model: str,
        system_prompt: str,
        tools: list[ToolUnionParam] | None = None,
        max_tokens: int = 4096,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.max_tokens = max_tokens
        self._client = client

    async def run(
        self,
        db: AsyncSession,
        ctx: BusinessContext,
        task: str,
    ) -> SpecialistResult:
        client = self._client or _anthropic_client()
        messages: list[MessageParam] = [{"role": "user", "content": task}]
        response = await client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.system_prompt,
            tools=self.tools,
            messages=messages,
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        cost = _cost_cents_for(
            self.model, response.usage.input_tokens, response.usage.output_tokens
        )
        return SpecialistResult(
            specialist=self.name,
            status="ok",
            summary=text,
            metadata={
                "model": self.model,
                "stop_reason": response.stop_reason,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            cost_cents=cost,
        )


class StubSpecialist:
    """Placeholder that returns a scripted 'not yet online' response.

    These preserve the specialist's voice so the CEO Agent can frame them
    coherently to the user — no hallucinating capability the stub doesn't have.
    """

    def __init__(
        self,
        *,
        name: str,
        persona_note: str,
        what_i_would_do: str,
        online_in: str = "a later session",
    ) -> None:
        self.name = name
        self._persona = persona_note
        self._what = what_i_would_do
        self._online_in = online_in

    async def run(
        self,
        db: AsyncSession,
        ctx: BusinessContext,
        task: str,
    ) -> SpecialistResult:
        return SpecialistResult(
            specialist=self.name,
            status="not_implemented",
            summary=(
                f"{self._persona} is not yet operational — coming online in "
                f"{self._online_in}. When live, I would: {self._what}"
            ),
            metadata={"task_received": task, "online_in": self._online_in},
            cost_cents=0,
        )


async def _hydrate_context(
    db: AsyncSession,
    user_id: uuid.UUID,
    business_id: uuid.UUID | None,
    session_id: uuid.UUID,
) -> BusinessContext:
    """Load the business + its brand_kit + active integrations + recent events
    into a `BusinessContext` so specialists have the state they need without
    going to DB themselves.

    Orchestrator-level calls (business_id=None) get a minimal context with the
    last 20 events on the session so Idea Scout et al. can see prior exchanges.
    """
    name = ""
    vertical = ""
    brand_kit: dict[str, Any] = {}
    integrations: tuple[str, ...] = ()

    if business_id is not None:
        biz_row = await db.execute(
            select(Business).where(Business.id == business_id, Business.user_id == user_id)
        )
        biz = biz_row.scalar_one_or_none()
        if biz is not None:
            name = biz.name
            vertical = biz.vertical
            brand_kit = dict(biz.brand_kit or {})

        integ_rows = (
            (
                await db.execute(
                    select(Integration.toolkit).where(
                        Integration.business_id == business_id,
                        Integration.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        integrations = tuple(integ_rows)

    # Recent events — last 20 on this session, newest first. Trimmed to the
    # fields a specialist actually needs (type + agent + short payload summary).
    event_rows = (
        (
            await db.execute(
                select(AgentEvent)
                .where(AgentEvent.session_id == session_id)
                .order_by(AgentEvent.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    events = tuple(
        {
            "timestamp": ev.created_at.isoformat(),
            "event_type": ev.event_type,
            "agent_name": ev.agent_name,
            "payload": dict(list(ev.payload.items())[:3]),
        }
        for ev in event_rows
    )

    return BusinessContext(
        user_id=user_id,
        business_id=business_id,
        business_name=name,
        vertical=vertical,
        brand_kit=brand_kit,
        connected_integrations=integrations,
        recent_events=events,
    )


# ────────────────────────────────────────────────────────────────────
# Registry — the CEO dispatches through this.
# ────────────────────────────────────────────────────────────────────

_REGISTRY: dict[str, Specialist] = {}


def register(specialist: Specialist) -> None:
    _REGISTRY[specialist.name] = specialist


def get(name: str) -> Specialist | None:
    return _REGISTRY.get(name)


def all_names() -> list[str]:
    return sorted(_REGISTRY.keys())


async def invoke(
    db: AsyncSession,
    session_id: uuid.UUID,
    specialist_name: str,
    task: str,
    user_id: uuid.UUID,
    business_id: uuid.UUID | None = None,
) -> SpecialistResult:
    """Single entry point used by `delegate_to_specialist`.

    Looks up the specialist, logs the invocation end-to-end to the event log
    with the specialist's `agent_name`, returns the structured result.
    """
    specialist = get(specialist_name)
    if specialist is None:
        return SpecialistResult(
            specialist=specialist_name,
            status="error",
            summary=f"Unknown specialist '{specialist_name}'. Available: {all_names()}",
            metadata={"available": all_names()},
            cost_cents=0,
        )

    ctx = await _hydrate_context(db, user_id, business_id, session_id)
    try:
        result = await specialist.run(db, ctx, task)
    except anthropic.APIError as e:
        return SpecialistResult(
            specialist=specialist_name,
            status="error",
            summary=f"{specialist_name} hit an Anthropic API error: {str(e)[:200]}",
            metadata={"error_type": type(e).__name__},
            cost_cents=0,
        )

    await event_log.write(
        db,
        session_id=session_id,
        business_id=business_id,
        event_type="specialist_completed",
        agent_name=specialist_name,
        payload={
            "task": task[:500],
            "status": result.status,
            "summary_preview": result.summary[:200],
        },
        cost_cents=result.cost_cents,
    )
    return result

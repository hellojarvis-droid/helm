"""Specialist framework.

A specialist is a focused sub-agent invoked by the CEO via `delegate_to_specialist`.

Session 6 additions:
  - BusinessContext.session_id — specialists can write event_log entries
  - LLMSpecialist runs a full tool-use loop (not single-shot) so it can use
    both Anthropic-native tools (web_search) and Composio tools in the same
    conversation
  - composio_toolkits parameter — toolkits the specialist may use when the
    business has them connected. Filtered against ctx.connected_integrations
    at run-time so we never ask Composio for tools from unconnected toolkits.

Invariants (enforced inside LLMSpecialist.run, not on callers):
  1. kill_switch.assert_not_set before every LLM call AND every tool call
  2. Every tool_use / tool_result gets an agent_events row with agent_name
     set to the specialist's own name
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, cast

import anthropic
import structlog
from anthropic.types import MessageParam, ToolUnionParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.config import get_settings
from helm.db.models import AgentEvent, Business, Integration
from helm.services import composio_client, event_log, kill_switch, tracing

log = structlog.get_logger("helm.specialists")

# Token costs per million (keep in sync with runtime._cost_cents).
_COSTS = {
    "claude-opus-4-7": (1500, 7500),
    "claude-sonnet-4-6": (300, 1500),
    "claude-haiku-4-5-20251001": (80, 400),
}

_MAX_TOOL_ITERATIONS = 8


@dataclass(frozen=True, slots=True)
class BusinessContext:
    """The slice of tenant + business state every specialist receives.

    session_id is the CEO Agent session this specialist call is nested under
    — specialists write their own tool_call / tool_result events against it,
    so the user can replay a specialist's work inside the outer conversation.
    """

    user_id: uuid.UUID
    business_id: uuid.UUID | None
    session_id: uuid.UUID
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
    """An LLM-backed specialist with a full tool-use loop.

    Tools come from three sources, all optional:
      - Anthropic server-side tools (web_search) declared via `tools=`
      - Composio tools — toolkits in `composio_toolkits` that are also in
        `ctx.connected_integrations` are loaded at run-time and merged in.
      - Just text: pass neither; the loop degrades to a single-shot call.

    The loop runs at most `_MAX_TOOL_ITERATIONS` iterations and respects the
    global kill switch between every turn.
    """

    def __init__(
        self,
        *,
        name: str,
        model: str,
        system_prompt: str,
        tools: list[ToolUnionParam] | None = None,
        composio_toolkits: list[str] | None = None,
        max_tokens: int = 4096,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.composio_toolkits = composio_toolkits or []
        self.max_tokens = max_tokens
        self._client = client

    async def run(
        self,
        db: AsyncSession,
        ctx: BusinessContext,
        task: str,
    ) -> SpecialistResult:
        client = self._client or _anthropic_client()
        tools, composio_slugs = await self._assemble_tools(ctx)

        messages: list[MessageParam] = [{"role": "user", "content": task}]
        input_tokens = 0
        output_tokens = 0
        final_text = ""
        final_stop_reason = "end_turn"

        for _iteration in range(_MAX_TOOL_ITERATIONS):
            await kill_switch.assert_not_set(db, ctx.user_id)
            try:
                response = await client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=self.system_prompt,
                    tools=tools,
                    messages=messages,
                )
            except anthropic.APIError as e:
                return SpecialistResult(
                    specialist=self.name,
                    status="error",
                    summary=f"{self.name} hit an Anthropic API error: {str(e)[:200]}",
                    metadata={"error_type": type(e).__name__},
                    cost_cents=_cost_cents_for(self.model, input_tokens, output_tokens),
                )

            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens
            final_stop_reason = response.stop_reason or "end_turn"

            # Pull text + tool_use blocks out of the response.
            assistant_content: list[dict[str, Any]] = []
            tool_uses: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    tu = {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                    assistant_content.append(tu)
                    tool_uses.append(tu)
                else:
                    assistant_content.append({"type": block.type, "raw": block.model_dump()})

            final_text = "".join(
                b.get("text", "") for b in assistant_content if b.get("type") == "text"
            )

            if final_stop_reason == "end_turn":
                break

            if final_stop_reason != "tool_use" or not tool_uses:
                # max_tokens / stop_sequence / unknown — no point continuing.
                break

            # Execute tools. Append assistant turn + tool_results as the next user turn.
            # Anthropic's MessageParam.content is a union of block TypedDicts —
            # our dicts match one of those variants by construction but mypy can't
            # prove it without per-block narrowing. Cast is the narrowest fix.
            messages.append(cast(MessageParam, {"role": "assistant", "content": assistant_content}))
            tool_results = await self._execute_tool_uses(
                db, ctx, tool_uses, composio_slugs=composio_slugs
            )
            messages.append(cast(MessageParam, {"role": "user", "content": tool_results}))

        cost_cents = _cost_cents_for(self.model, input_tokens, output_tokens)
        tracing.record_generation(
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            business_id=ctx.business_id,
            agent_name=self.name,
            model=self.model,
            input_messages=cast(list[dict[str, Any]], messages[-5:]),
            output_text=final_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_cents=cost_cents,
            metadata={
                "stop_reason": final_stop_reason,
                "composio_tools_available": bool(composio_slugs),
            },
        )
        return SpecialistResult(
            specialist=self.name,
            status="ok",
            summary=final_text,
            metadata={
                "model": self.model,
                "stop_reason": final_stop_reason,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "composio_tools_available": bool(composio_slugs),
            },
            cost_cents=cost_cents,
        )

    # ────────────────────────────────────────────────────────────────
    # Internals
    # ────────────────────────────────────────────────────────────────

    async def _assemble_tools(
        self, ctx: BusinessContext
    ) -> tuple[list[ToolUnionParam], frozenset[str]]:
        """Return the full tool list for this invocation + the set of Composio
        slugs so the dispatcher knows which branch to take on tool_use.

        Composio toolkits the specialist CAN use are intersected with the
        business's connected toolkits — we never ask Composio for tools from
        toolkits the user hasn't authorized.
        """
        tools: list[ToolUnionParam] = list(self.tools)
        composio_slugs: set[str] = set()

        usable = [t for t in self.composio_toolkits if t in ctx.connected_integrations]
        if usable:
            try:
                raw = await composio_client.list_tools(
                    user_id=ctx.user_id,
                    business_id=ctx.business_id,
                    toolkits=usable,
                )
            except Exception as e:  # SDK / network — log and proceed without.
                log.warning("specialist.composio_list_failed", err=str(e), toolkits=usable)
                raw = []
            params = composio_client.tools_as_anthropic_params(raw)
            for p in params:
                # Composio tool dicts match the Anthropic ToolParam shape by
                # construction (name/description/input_schema); mypy needs a cast.
                tools.append(cast(ToolUnionParam, p))
                composio_slugs.add(p["name"])

        return tools, frozenset(composio_slugs)

    async def _execute_tool_uses(
        self,
        db: AsyncSession,
        ctx: BusinessContext,
        tool_uses: list[dict[str, Any]],
        *,
        composio_slugs: frozenset[str],
    ) -> list[dict[str, Any]]:
        """Execute every tool_use block from one assistant turn, log each,
        return the tool_result content blocks to feed back to the model."""
        results: list[dict[str, Any]] = []
        for tu in tool_uses:
            await kill_switch.assert_not_set(db, ctx.user_id)
            name = tu["name"]
            args = tu.get("input") or {}

            await event_log.write(
                db,
                session_id=ctx.session_id,
                business_id=ctx.business_id,
                event_type="tool_call",
                agent_name=self.name,
                payload={"name": name, "input": args},
            )

            if name in composio_slugs:
                try:
                    result = await composio_client.execute_tool(
                        tool_slug=name,
                        arguments=args,
                        user_id=ctx.user_id,
                        business_id=ctx.business_id,
                    )
                    is_error = False
                except Exception as e:  # surface to the model as tool_result error
                    log.exception("specialist.composio_execute_failed", tool=name)
                    result = {"error": str(e)[:400]}
                    is_error = True
            else:
                # Not a Composio tool → Anthropic handled it server-side
                # (web_search etc.). The server embeds the result in the next
                # message; we'd never see a client-side tool_use for it.
                result = {
                    "error": (
                        f"Specialist {self.name} received a client-side tool_use for "
                        f"'{name}' but has no implementation for it. Ignoring."
                    )
                }
                is_error = True

            await event_log.write(
                db,
                session_id=ctx.session_id,
                business_id=ctx.business_id,
                event_type="tool_result",
                agent_name=self.name,
                payload={"name": name, "result": result, "is_error": is_error},
            )

            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": json.dumps(result),
                    "is_error": is_error,
                }
            )
        return results


class StubSpecialist:
    """Placeholder that returns a scripted 'not yet online' response."""

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
    into a `BusinessContext`.
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
        session_id=session_id,
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
    """Single entry point used by `delegate_to_specialist`."""
    specialist = get(specialist_name)
    if specialist is None:
        return SpecialistResult(
            specialist=specialist_name,
            status="error",
            summary=f"Unknown specialist '{specialist_name}'. Available: {all_names()}",
            metadata={"available": all_names()},
            cost_cents=0,
        )

    if business_id is not None:
        owns_business = (
            await db.execute(
                select(Business.id).where(Business.id == business_id, Business.user_id == user_id)
            )
        ).scalar_one_or_none()
        if owns_business is None:
            return SpecialistResult(
                specialist=specialist_name,
                status="error",
                summary="business not found for this user",
                metadata={},
                cost_cents=0,
            )

    ctx = await _hydrate_context(db, user_id, business_id, session_id)
    try:
        result = await specialist.run(db, ctx, task)
    except kill_switch.KillSwitchActivated:
        return SpecialistResult(
            specialist=specialist_name,
            status="error",
            summary="Kill switch is on — specialist halted mid-run.",
            metadata={"reason": "kill_switch_activated"},
            cost_cents=0,
        )
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

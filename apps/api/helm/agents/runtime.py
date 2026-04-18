"""Agent runtime — Messages-API implementation.

MessagesRuntime drives Claude's stable Messages API with:
  - server-side text streaming (token-by-token text_delta events)
  - a local tool-use loop (server stops with stop_reason='tool_use', we
    execute the tool, feed the result back, loop)
  - specialist delegation (the `delegate_to_specialist` tool reaches into
    `helm.agents.specialists.base.invoke`)
  - kill-switch checks before every LLM call AND every tool call
  - full event-sourcing: every user msg, agent response, tool_call, tool_result,
    approval_requested gets a row in `agent_events`

A `ManagedAgentsRuntime` (client.beta.agents + sessions) can later plug in
behind the same `ChatEvent` interface; the route code doesn't care which runs.

Invariants:
  1. `kill_switch.assert_not_set` runs before every LLM call and every tool call.
  2. `agent_events` captures every turn-relevant action.
  3. History sent to Claude on each turn is rebuilt from `agent_events` — the
     process holds no conversation state across requests.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import anthropic
import structlog
from anthropic.types import MessageParam, RawContentBlockDeltaEvent, TextDelta, ToolUnionParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Side-effect: registering every specialist at module load so `delegate_to_specialist`
# can find them without further wiring.
import helm.agents.specialists.registry  # noqa: F401
from helm.agents.tools import CEO_TOOL_IMPLS, CEO_TOOLS, ToolContext
from helm.config import get_settings
from helm.db.models import AgentEvent
from helm.services import event_log, kill_switch, tracing, usage_reporter

log = structlog.get_logger("helm.runtime")

_CEO_MODEL = "claude-opus-4-7"
_MAX_TOKENS = 8192
_MAX_TOOL_ITERATIONS = 6

_PROMPTS_DIR = Path(__file__).parent / "prompts"


# ────────────────────────────────────────────────────────────────────
# Public event shape
# ────────────────────────────────────────────────────────────────────


EventKind = Literal[
    "user_logged",
    "text_delta",
    "tool_call",
    "tool_result",
    "approval_requested",
    "turn_cost",
    "done",
    "error",
]


@dataclass(frozen=True, slots=True)
class ChatEvent:
    kind: EventKind
    data: dict[str, Any]

    def to_sse(self) -> str:
        # Event kind is the source of truth; put it last so data keys named
        # "kind" (e.g. the approval's own `kind` field) can't clobber it.
        payload = json.dumps({**self.data, "kind": self.kind}, default=str)
        return f"data: {payload}\n\n"


# ────────────────────────────────────────────────────────────────────
# Runtime
# ────────────────────────────────────────────────────────────────────


@dataclass
class _TurnState:
    session_id: uuid.UUID
    user_id: uuid.UUID
    business_id: uuid.UUID | None
    messages: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class MessagesRuntime:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        self._client = client or anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)
        self._system_prompt = (_PROMPTS_DIR / "ceo_agent.md").read_text()

    async def stream_turn(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        business_id: uuid.UUID | None,
        user_message: str,
    ) -> AsyncIterator[ChatEvent]:
        # Always log the user's message first. The event log is the authoritative
        # record of what the user asked — even if the kill switch blocks the
        # response, the user message is in the log and the next turn can see it.
        await event_log.write(
            db,
            session_id=session_id,
            event_type="message.user",
            agent_name="user",
            payload={"text": user_message},
            business_id=business_id,
        )
        yield ChatEvent("user_logged", {"text": user_message})

        state = _TurnState(session_id=session_id, user_id=user_id, business_id=business_id)

        try:
            await kill_switch.assert_not_set(db, user_id)
            state.messages = await self._load_history(db, session_id)
            state.messages.append({"role": "user", "content": user_message})

            for iteration in range(_MAX_TOOL_ITERATIONS):
                await kill_switch.assert_not_set(db, user_id)

                assistant_content: list[dict[str, Any]] = []
                stop_reason = "end_turn"

                # Stream one LLM call. Yield text deltas as they arrive;
                # collect the final assembled message for logging + tool routing.
                async with self._client.messages.stream(
                    model=_CEO_MODEL,
                    max_tokens=_MAX_TOKENS,
                    system=self._system_prompt,
                    tools=cast("list[ToolUnionParam]", CEO_TOOLS),
                    messages=cast("list[MessageParam]", state.messages),
                ) as stream:
                    async for event in stream:
                        if isinstance(event, RawContentBlockDeltaEvent) and isinstance(
                            event.delta, TextDelta
                        ):
                            yield ChatEvent("text_delta", {"text": event.delta.text})
                    final = await stream.get_final_message()

                state.input_tokens += final.usage.input_tokens
                state.output_tokens += final.usage.output_tokens
                stop_reason = final.stop_reason or "end_turn"

                for block in final.content:
                    if block.type == "text":
                        assistant_content.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        assistant_content.append(
                            {
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            }
                        )
                    else:
                        # web_search_tool_result, etc. — round-trip via model_dump
                        assistant_content.append({"type": block.type, "raw": block.model_dump()})

                if stop_reason == "end_turn":
                    await self._log_agent_text(db, state, assistant_content)
                    break

                if stop_reason == "tool_use":
                    await self._log_agent_text(db, state, assistant_content)
                    state.messages.append({"role": "assistant", "content": assistant_content})
                    tool_results: list[dict[str, Any]] = []
                    async for ev in self._run_tools(db, state, assistant_content, tool_results):
                        yield ev
                    state.messages.append({"role": "user", "content": tool_results})
                    continue

                # max_tokens / stop_sequence / unknown — bail.
                log.warning("turn.unexpected_stop", stop_reason=stop_reason, iter=iteration)
                await self._log_agent_text(db, state, assistant_content)
                break

            yield ChatEvent(
                "turn_cost",
                {
                    "input_tokens": state.input_tokens,
                    "output_tokens": state.output_tokens,
                    "cost_cents": _cost_cents(state.input_tokens, state.output_tokens),
                },
            )
            # Fire-and-forget metered-usage report. No-op when the user has
            # no metered SubscriptionItem or when Stripe isn't configured.
            usage_reporter.schedule_report(str(user_id))
            yield ChatEvent("done", {})
        except kill_switch.KillSwitchActivated:
            await event_log.write(
                db,
                session_id=session_id,
                event_type="kill_switch_activated",
                agent_name="runtime",
                payload={},
                business_id=business_id,
            )
            yield ChatEvent("error", {"reason": "kill_switch_activated"})
        except anthropic.APIError as e:
            log.error("turn.anthropic_error", err=str(e))
            await event_log.write(
                db,
                session_id=session_id,
                event_type="error",
                agent_name="runtime",
                payload={"kind": "anthropic_api", "detail": str(e)[:500]},
                business_id=business_id,
            )
            yield ChatEvent("error", {"reason": "anthropic_api", "detail": str(e)[:200]})

    # ────────────────────────────────────────────────────────────────
    # Internals
    # ────────────────────────────────────────────────────────────────

    async def _run_tools(
        self,
        db: AsyncSession,
        state: _TurnState,
        assistant_content: list[dict[str, Any]],
        tool_results_out: list[dict[str, Any]],
    ) -> AsyncIterator[ChatEvent]:
        for block in assistant_content:
            if block["type"] != "tool_use":
                continue

            name = block["name"]
            tool_use_id = block["id"]
            args = block.get("input") or {}

            await kill_switch.assert_not_set(db, state.user_id)
            await event_log.write(
                db,
                session_id=state.session_id,
                event_type="tool_call",
                agent_name="ceo_agent",
                payload={"name": name, "input": args},
                business_id=state.business_id,
            )
            yield ChatEvent("tool_call", {"name": name, "input": args})

            impl = CEO_TOOL_IMPLS.get(name)
            tool_ctx = ToolContext(
                db=db,
                session_id=state.session_id,
                user_id=state.user_id,
                business_id=state.business_id,
            )

            if impl is None:
                result: dict[str, Any] = {"error": f"tool '{name}' not implemented"}
                is_error = True
            else:
                try:
                    result = await impl(tool_ctx, args)
                    is_error = bool(result.get("error"))
                except Exception as exc:  # bubble into model's tool_result, don't crash turn
                    log.exception("tool.failed", name=name)
                    result = {"error": str(exc)[:400]}
                    is_error = True

            # Side-channel events (e.g. approval_requested) flushed after tool_result.
            await event_log.write(
                db,
                session_id=state.session_id,
                event_type="tool_result",
                agent_name="ceo_agent",
                payload={"name": name, "result": result, "is_error": is_error},
                business_id=state.business_id,
            )
            yield ChatEvent("tool_result", {"name": name, "is_error": is_error})

            for ev in tool_ctx.events_out:
                yield ev

            tool_results_out.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps(result),
                    "is_error": is_error,
                }
            )

    async def _log_agent_text(
        self, db: AsyncSession, state: _TurnState, content: list[dict[str, Any]]
    ) -> None:
        text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
        if not text.strip() and not any(b.get("type") == "tool_use" for b in content):
            return
        cost_cents = _cost_cents(state.input_tokens, state.output_tokens)
        await event_log.write(
            db,
            session_id=state.session_id,
            event_type="message.agent",
            agent_name="ceo_agent",
            payload={"text": text, "content_blocks": content},
            business_id=state.business_id,
            cost_cents=cost_cents,
        )
        tracing.record_generation(
            session_id=state.session_id,
            user_id=state.user_id,
            business_id=state.business_id,
            agent_name="ceo_agent",
            model=_CEO_MODEL,
            input_messages=state.messages[-5:],  # trailing context only
            output_text=text,
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            cost_cents=cost_cents,
        )

    async def _load_history(self, db: AsyncSession, session_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await db.execute(
            select(AgentEvent)
            .where(
                AgentEvent.session_id == session_id,
                AgentEvent.event_type.in_(["message.user", "message.agent"]),
            )
            .order_by(AgentEvent.created_at.asc())
        )
        events = list(result.scalars().all())
        messages: list[dict[str, Any]] = []
        for ev in events:
            if ev.event_type == "message.user":
                messages.append({"role": "user", "content": ev.payload.get("text", "")})
            elif ev.event_type == "message.agent":
                blocks = ev.payload.get("content_blocks") or [
                    {"type": "text", "text": ev.payload.get("text", "")}
                ]
                messages.append({"role": "assistant", "content": blocks})
        return messages


def _cost_cents(input_tokens: int, output_tokens: int) -> int:
    """Opus 4.7: $15/M input, $75/M output. Cents, rounded."""
    cents = (input_tokens * 15 + output_tokens * 75) / 10_000
    return int(cents + 0.5)


_default: MessagesRuntime | None = None


def default_runtime() -> MessagesRuntime:
    global _default
    if _default is None:
        _default = MessagesRuntime()
    return _default

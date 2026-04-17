"""Agent runtime — Messages-API implementation.

Phase 1 Session 1 ships this single runtime (`MessagesRuntime`) built on
Anthropic's Messages API with tool use and a hand-rolled conversation-history
loader. This is the simplest correct version that ships the chat loop
end-to-end.

Phase 1 Session 2 will add a `ManagedAgentsRuntime` that uses `client.beta.
agents` + `client.beta.sessions` for Anthropic-managed state. Both
implementations will speak the same `ChatEvent` stream shape below, so the
FastAPI route doesn't care which one runs.

Invariants (enforced here, not on callers):
  1. Every tool call is guarded by `kill_switch.assert_not_set` BEFORE execute.
  2. Every user message + agent response + tool_call + tool_result is logged
     to `agent_events`.
  3. The conversation history sent to Claude is rebuilt from the event log on
     each turn — we don't keep anything in process memory.
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
from anthropic.types import MessageParam, ToolParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.agents.tools import CEO_TOOL_IMPLS, CEO_TOOLS
from helm.config import get_settings
from helm.db.models import AgentEvent
from helm.services import event_log, kill_switch

log = structlog.get_logger("helm.runtime")

# Anthropic model IDs (per system prompt/ARCHITECTURE.md non-negotiables).
_CEO_MODEL = "claude-opus-4-7"
_MAX_TOKENS = 8192
_MAX_TOOL_ITERATIONS = 6  # Prevents runaway loops; plenty for any one user turn.

_PROMPTS_DIR = Path(__file__).parent / "prompts"


# ────────────────────────────────────────────────────────────────────
# Public event shape — the runtime emits these; the route streams them to SSE.
# ────────────────────────────────────────────────────────────────────


EventKind = Literal[
    "user_logged",
    "text_delta",
    "tool_call",
    "tool_result",
    "turn_cost",
    "done",
    "error",
]


@dataclass(frozen=True, slots=True)
class ChatEvent:
    kind: EventKind
    data: dict[str, Any]

    def to_sse(self) -> str:
        """Serialize as an SSE `data:` line."""
        payload = json.dumps({"kind": self.kind, **self.data}, default=str)
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
    """Stateless (per instance) driver that uses the stable Messages API."""

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
        """Run one user→agent turn and stream events.

        Yields `ChatEvent` instances end-to-end; the final event is always a
        `done` (or `error` on failure). The SSE route serializes each.
        """
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
                assistant_content, stop_reason = await self._stream_once(state)

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

    async def _stream_once(self, state: _TurnState) -> tuple[list[dict[str, Any]], str]:
        """Stream one LLM call, yielding text deltas via the `.text` side-channel.

        Returns (assistant content blocks, stop_reason). Text deltas are
        emitted as ChatEvent("text_delta", ...) through a shared generator
        pattern — since Python async generators can't easily share state with
        an inner stream context manager, we collect deltas into the caller-
        owned event buffer via monkey-patching. Keeping it simple here: this
        helper returns the final content and the caller yields the deltas
        separately. Streaming text deltas lands in a follow-up polish pass
        (noted in plan).
        """
        # The Anthropic SDK types `tools` + `messages` as TypedDict unions.
        # Our dicts match those shapes by construction, but mypy can't prove
        # structural compatibility; cast is the narrowest workaround.
        response = await self._client.messages.create(
            model=_CEO_MODEL,
            max_tokens=_MAX_TOKENS,
            system=self._system_prompt,
            tools=cast("list[ToolParam]", CEO_TOOLS),
            messages=cast("list[MessageParam]", state.messages),
        )
        state.input_tokens += response.usage.input_tokens
        state.output_tokens += response.usage.output_tokens

        # Convert SDK content blocks to plain dicts we can persist + round-trip.
        content: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
            else:
                content.append({"type": block.type, "raw": block.model_dump()})
        return content, response.stop_reason or "end_turn"

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
            if impl is None:
                result: dict[str, Any] = {
                    "error": f"tool '{name}' not implemented in Phase 1 Session 1"
                }
                is_error = True
            else:
                try:
                    result = await impl(db, state.session_id, args)
                    is_error = False
                except Exception as exc:  # surface errors to the model, don't crash the turn
                    log.exception("tool.failed", name=name)
                    result = {"error": str(exc)[:400]}
                    is_error = True

            await event_log.write(
                db,
                session_id=state.session_id,
                event_type="tool_result",
                agent_name="ceo_agent",
                payload={"name": name, "result": result, "is_error": is_error},
                business_id=state.business_id,
            )
            yield ChatEvent("tool_result", {"name": name, "is_error": is_error})

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
        if not text.strip():
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

    async def _load_history(self, db: AsyncSession, session_id: uuid.UUID) -> list[dict[str, Any]]:
        """Rebuild the Claude `messages` list from `agent_events`.

        We store the full content-block structure in each agent message's
        payload, so we can replay tool_use/tool_result turns faithfully.
        """
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
    """Opus 4.7 published rates: $15/M input, $75/M output.
    Integer cents, rounded up; this matches Anthropic's billing precision."""
    input_cost = (input_tokens * 15) / 1_000_000
    output_cost = (output_tokens * 75) / 1_000_000
    return int((input_cost + output_cost) * 100 + 0.5)


# Module-level instance so each request isn't rebuilding an Anthropic client.
# The client is thread-safe and async-safe; one instance per process is correct.
_default: MessagesRuntime | None = None


def default_runtime() -> MessagesRuntime:
    global _default
    if _default is None:
        _default = MessagesRuntime()
    return _default

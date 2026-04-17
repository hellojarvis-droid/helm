"""CEO Agent's built-in tools (Phase 1 Session 1).

Tools that don't require a specialist or external integration. Specialist
delegation and Composio-backed tools land in Session 2.

Each tool:
  - is declared once in `CEO_TOOLS` with its JSON schema
  - has an async `execute_*` implementation that takes a dict of arguments
  - returns a plain dict (JSON-serializable) — the runtime renders it as a
    tool_result content block
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from helm.services import event_log

# ────────────────────────────────────────────────────────────────────
# Tool declarations (passed to client.messages.create as-is)
# ────────────────────────────────────────────────────────────────────

CEO_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_current_time",
        "description": (
            "Return the current UTC wall-clock time in ISO 8601 format. "
            "Use this when you need to reason about recency or build a timestamped report."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "query_event_log",
        "description": (
            "Fetch the agent's own recent events for the current session. "
            "Use this to answer 'what did you do recently?' or to build a summary of actions. "
            "Returns a list of {timestamp, event_type, agent_name, payload_summary}."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of events to return, newest first. Default 20.",
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": [],
        },
    },
]


# ────────────────────────────────────────────────────────────────────
# Implementations
# ────────────────────────────────────────────────────────────────────


async def execute_get_current_time(
    db: AsyncSession,
    session_id: uuid.UUID,
    args: dict[str, Any],
) -> dict[str, Any]:
    return {"utc_iso": datetime.now(UTC).isoformat()}


async def execute_query_event_log(
    db: AsyncSession,
    session_id: uuid.UUID,
    args: dict[str, Any],
) -> dict[str, Any]:
    limit = int(args.get("limit", 20))
    events = await event_log.recent_for_session(db, session_id, limit=limit)
    return {
        "count": len(events),
        "events": [
            {
                "timestamp": e.created_at.isoformat(),
                "event_type": e.event_type,
                "agent_name": e.agent_name,
                "payload_summary": _summarize(e.payload),
            }
            for e in events
        ],
    }


# Map name → impl for the runtime dispatcher
CEO_TOOL_IMPLS: dict[str, Any] = {
    "get_current_time": execute_get_current_time,
    "query_event_log": execute_query_event_log,
}


def _summarize(payload: dict[str, Any]) -> str:
    """Don't dump full payloads back to the model — it'd tokenize heavily and
    expose structure the model doesn't need. One-line human summary."""
    if "text" in payload:
        text = str(payload["text"])
        return text[:200] + ("…" if len(text) > 200 else "")
    if "name" in payload:
        return f"{payload.get('name', '?')}({list(payload.get('input', {}).keys())})"
    return ", ".join(f"{k}={v}" for k, v in list(payload.items())[:3])

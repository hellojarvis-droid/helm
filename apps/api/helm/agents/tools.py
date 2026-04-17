"""CEO Agent's tools.

Session 2 tools:
  - get_current_time (trivial)
  - query_event_log (read-only, scope: current session)
  - delegate_to_specialist (the orchestrator primitive)
  - request_user_approval (insert row + emit SSE event)

Every tool implementation takes a `ToolContext` carrying the tenant scope, the
DB session, and an output list for side-channel SSE events (used by the
approval tool). This replaces the Session 1 signature (db, session_id, args).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from helm.agents.specialists.base import invoke as invoke_specialist
from helm.db.models import Approval
from helm.services import event_log

if TYPE_CHECKING:
    from helm.agents.runtime import ChatEvent


@dataclass(slots=True)
class ToolContext:
    """Everything a tool needs to execute one invocation."""

    db: AsyncSession
    session_id: uuid.UUID
    user_id: uuid.UUID
    business_id: uuid.UUID | None
    events_out: list[ChatEvent] = field(default_factory=list)


class ToolFn(Protocol):
    async def __call__(self, ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]: ...


# ────────────────────────────────────────────────────────────────────
# Tool declarations
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
            "Fetch this session's recent agent events. "
            "Use to answer 'what did you do recently?' or summarize actions. "
            "Returns {count, events:[{timestamp, event_type, agent_name, payload_summary}]}."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max events, newest-first. Default 20.",
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": [],
        },
    },
    {
        "name": "delegate_to_specialist",
        "description": (
            "Send a focused task to a specialist sub-agent and receive a structured "
            "result. Use this any time the work needs a domain-specific specialist "
            "rather than your own reasoning.\n\n"
            "AVAILABLE specialists (use these exact names):\n"
            "  - idea_scout: finds PROVEN business ideas with sourced evidence (real, online).\n"
            "  - product_builder: launches Shopify stores end-to-end (Session 3).\n"
            "  - creative_director: brand kit + copy + ad creative (Session 3).\n"
            "  - ads_operator: runs Meta/Google/TikTok paid media (Session 4).\n"
            "  - social_engagement: replies to organic social (Session 5).\n"
            "  - customer_service: handles tickets + refunds (Session 5).\n"
            "  - finance_ops: reconciliation + P&L + card monitoring (Session 6).\n"
            "  - growth_analyst: weekly strategic review + anomaly detection (Session 4).\n\n"
            "Specialists not yet 'online' return a scripted 'what I would do' response "
            "— relay that to the user honestly; don't fake the work."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "specialist_name": {
                    "type": "string",
                    "description": "Exactly one of the registered names above.",
                },
                "task": {
                    "type": "string",
                    "description": (
                        "Clear, self-contained instruction for the specialist. "
                        "Include any constraints the user gave you."
                    ),
                },
                "business_id": {
                    "type": "string",
                    "description": (
                        "UUID of the business this work is scoped to. Optional for "
                        "idea_scout (pre-launch) but required for anything that "
                        "writes to a specific business."
                    ),
                },
            },
            "required": ["specialist_name", "task"],
        },
    },
    {
        "name": "request_user_approval",
        "description": (
            "Ask the user to approve or modify a proposed action BEFORE you do it. "
            "Use this for: spend > $100, launching a new campaign, publishing "
            "customer-facing content, deleting data, opening a new business, or "
            "anything else the user should sign off on. Returns {approval_id, "
            "status: 'pending'}. The CEO must not proceed with the action until "
            "the user responds; the response arrives on the next chat turn."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["spend", "publish", "delete", "other"],
                    "description": "Category of action for UI grouping.",
                },
                "summary": {
                    "type": "string",
                    "description": (
                        "One-sentence human-readable description of the action, with "
                        "expected impact and cost. Example: "
                        "'Spend $340 on 3 TikTok creatives targeting 25-34 home-decor, "
                        "expected ROAS 2.1-2.8, auto-pause if < 1.5 at 48h.'"
                    ),
                },
                "details": {
                    "type": "object",
                    "description": "Structured payload the UI can render (numbers, URLs, etc.).",
                },
                "business_id": {
                    "type": "string",
                    "description": "UUID of the business this approval scopes to.",
                },
                "expires_in_hours": {
                    "type": "integer",
                    "description": "How long until this approval auto-expires. Default 24.",
                    "minimum": 1,
                    "maximum": 168,
                },
            },
            "required": ["kind", "summary", "business_id"],
        },
    },
]


# ────────────────────────────────────────────────────────────────────
# Implementations
# ────────────────────────────────────────────────────────────────────


async def _get_current_time(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {"utc_iso": datetime.now(UTC).isoformat()}


async def _query_event_log(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit", 20))
    events = await event_log.recent_for_session(ctx.db, ctx.session_id, limit=limit)
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


async def _delegate_to_specialist(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    name = args["specialist_name"]
    task = args["task"]
    biz_arg = args.get("business_id")
    biz_id: uuid.UUID | None = None
    if isinstance(biz_arg, str) and biz_arg:
        try:
            biz_id = uuid.UUID(biz_arg)
        except ValueError:
            return {
                "status": "error",
                "summary": f"business_id '{biz_arg}' is not a valid UUID",
                "metadata": {},
                "cost_cents": 0,
            }

    result = await invoke_specialist(
        ctx.db,
        session_id=ctx.session_id,
        specialist_name=name,
        task=task,
        user_id=ctx.user_id,
        business_id=biz_id,
    )
    return result.to_dict()


async def _request_user_approval(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from helm.agents.runtime import ChatEvent  # local import avoids circular

    biz_arg = args.get("business_id")
    if not isinstance(biz_arg, str) or not biz_arg:
        return {"status": "error", "summary": "business_id is required"}
    try:
        biz_id = uuid.UUID(biz_arg)
    except ValueError:
        return {"status": "error", "summary": f"business_id '{biz_arg}' is not a valid UUID"}

    expires_hours = int(args.get("expires_in_hours", 24))
    row = Approval(
        business_id=biz_id,
        kind=args.get("kind", "other"),
        summary=args["summary"],
        details=args.get("details") or {},
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(hours=expires_hours),
    )
    ctx.db.add(row)
    await ctx.db.commit()
    await ctx.db.refresh(row)

    await event_log.write(
        ctx.db,
        session_id=ctx.session_id,
        business_id=biz_id,
        event_type="approval_requested",
        agent_name="ceo_agent",
        payload={
            "approval_id": str(row.id),
            "kind": row.kind,
            "summary": row.summary,
        },
    )

    ctx.events_out.append(
        ChatEvent(
            "approval_requested",
            {
                "approval_id": str(row.id),
                "approval_kind": row.kind,
                "summary": row.summary,
                "business_id": str(biz_id),
                "expires_at": row.expires_at.isoformat(),
            },
        )
    )

    return {
        "approval_id": str(row.id),
        "status": "pending",
        "expires_at": row.expires_at.isoformat(),
        "note": "Do not execute the proposed action until the user responds.",
    }


CEO_TOOL_IMPLS: dict[str, ToolFn] = {
    "get_current_time": _get_current_time,
    "query_event_log": _query_event_log,
    "delegate_to_specialist": _delegate_to_specialist,
    "request_user_approval": _request_user_approval,
}


def _summarize(payload: dict[str, Any]) -> str:
    if "text" in payload:
        text = str(payload["text"])
        return text[:200] + ("…" if len(text) > 200 else "")
    if "name" in payload:
        return f"{payload.get('name', '?')}({list(payload.get('input', {}).keys())})"
    return ", ".join(f"{k}={v}" for k, v in list(payload.items())[:3])

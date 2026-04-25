"""CEO Agent's tools.

Tools the CEO Agent can invoke mid-turn:
  - get_current_time (trivial)
  - query_event_log (read-only, scope: current session)
  - delegate_to_specialist (the orchestrator primitive)
  - request_user_approval (insert row + emit SSE event)
  - create_business (insert businesses row, after approval)
  - request_spend (record spending intent before a merchant purchase)
  - escalate_to_computer_use (queue a desktop sandbox task)

Every tool implementation takes a `ToolContext` carrying the tenant scope, the
DB session, and an output list for side-channel SSE events (used by the
approval tool).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.agents.specialists.base import invoke as invoke_specialist
from helm.db.models import Approval, Business, User
from helm.services import event_log, push

_VERTICALS = {"dtc_physical", "dtc_pod", "saas", "services"}
_APPROVAL_KINDS = ("spend", "publish", "delete", "other")

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
        "name": "create_business",
        "description": (
            "Create a new business row for this user. CLAUDE.md requires approval "
            "before opening a new business — you MUST call request_user_approval FIRST "
            "and confirm an approval_granted event in the log before invoking this tool.\n\n"
            "Returns {business_id, name, vertical, status}. Once created, you typically "
            "follow up by delegating to creative_director with a brand-kit task and, "
            "when online, product_builder to stand up the storefront."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short, memorable business name (1-120 chars).",
                    "minLength": 1,
                    "maxLength": 120,
                },
                "vertical": {
                    "type": "string",
                    "enum": sorted(_VERTICALS),
                    "description": "Business vertical. Most will be 'dtc_physical'.",
                },
                "weekly_spend_cap_cents": {
                    "type": "integer",
                    "description": (
                        "Hard weekly spending cap the Stripe Issuing card will enforce. "
                        "Default $500 = 50000 cents. Raise with explicit approval only."
                    ),
                    "minimum": 0,
                    "maximum": 10000000,
                },
            },
            "required": ["name", "vertical"],
        },
    },
    {
        "name": "request_spend",
        "description": (
            "Record spending intent BEFORE initiating a merchant purchase with "
            "the business's Stripe-issued card. Writes a `spend_intent` event "
            "linked to the business, with amount + merchant_hint + purpose. "
            "When Stripe later sends the real authorization request on the "
            "merchant's charge, our webhook correlates it to the intent as "
            "defense-in-depth against an agent going off-script.\n\n"
            "You still must call request_user_approval FIRST for any spend that "
            "crosses an approval threshold — this tool records the intent, it "
            "does NOT perform the charge. Stripe does that when the merchant "
            "submits the actual transaction.\n\n"
            "Returns {intent_id, ok}."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "business_id": {
                    "type": "string",
                    "description": "UUID of the business whose card will be charged.",
                },
                "amount_cents": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10000000,
                    "description": "Expected charge in cents (e.g. 34000 = $340.00).",
                },
                "merchant_hint": {
                    "type": "string",
                    "description": (
                        "Who you expect to charge (e.g. 'Meta Ads', 'Printful'). "
                        "The real merchant_data in the Stripe authorization may differ "
                        "slightly; this is a hint for correlation."
                    ),
                },
                "purpose": {
                    "type": "string",
                    "description": (
                        "One-sentence reason for the spend. Lands in the event log "
                        "and the audit trail. Example: 'Meta Smart+ test for "
                        "candle-store launch, 72h run, $340 total.'"
                    ),
                },
            },
            "required": ["business_id", "amount_cents", "merchant_hint", "purpose"],
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
                    "enum": list(_APPROVAL_KINDS),
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
    {
        "name": "escalate_to_computer_use",
        "description": (
            "Queue a task that needs the user's screen — for sites without a "
            "usable API, or where Composio's coverage is incomplete. The task "
            "runs in the desktop app's sandboxed computer-use session when the "
            "user has it open; otherwise it queues for the next time they do. "
            "Use ONLY when no Composio toolkit + no specialist can complete "
            "the work via API. Examples: TikTok Ads small-budget self-serve "
            "flow, supplier portals without Shopify integration.\n\n"
            "Returns {escalation_id, status: 'queued'}. You should still tell "
            "the user the agent will hand the task to their desktop — they need "
            "to know they may be asked to watch the screen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "business_id": {
                    "type": "string",
                    "description": "UUID of the business this task is scoped to.",
                },
                "task": {
                    "type": "string",
                    "description": (
                        "Self-contained instruction for the computer-use sandbox. "
                        "Include success criteria so the run knows when it's done."
                    ),
                },
                "app_hint": {
                    "type": "string",
                    "description": (
                        "Which app / site the sandbox should open first. "
                        "Examples: 'tiktok ads manager', 'printful catalog'."
                    ),
                },
            },
            "required": ["business_id", "task", "app_hint"],
        },
    },
]


# ────────────────────────────────────────────────────────────────────
# Implementations
# ────────────────────────────────────────────────────────────────────


def _parse_business_id(args: dict[str, Any]) -> uuid.UUID | dict[str, Any]:
    """Return a UUID on success, an error-shaped dict on failure."""
    biz_arg = args.get("business_id")
    if not isinstance(biz_arg, str) or not biz_arg:
        return {"status": "error", "summary": "business_id is required"}
    try:
        return uuid.UUID(biz_arg)
    except ValueError:
        return {
            "status": "error",
            "summary": f"business_id '{biz_arg}' is not a valid UUID",
        }


async def _resolve_owned_business(
    ctx: ToolContext, args: dict[str, Any]
) -> uuid.UUID | dict[str, Any]:
    """Parse business_id and confirm it belongs to the caller.

    The CEO session is already user-scoped, but tool args come from the
    model — verify ownership before any write.
    """
    parsed = _parse_business_id(args)
    if isinstance(parsed, dict):
        return parsed
    row = await ctx.db.execute(
        select(Business.id).where(Business.id == parsed, Business.user_id == ctx.user_id)
    )
    if row.scalar_one_or_none() is None:
        return {"status": "error", "summary": "business not found for this user"}
    return parsed


def _require_str(args: dict[str, Any], key: str) -> str | dict[str, Any]:
    val = args.get(key)
    if not isinstance(val, str) or not val.strip():
        return {"status": "error", "summary": f"{key} is required"}
    return val.strip()


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
    # Note: this tool keeps its own UUID parsing because it returns a
    # specialist-shaped error envelope (with `metadata` + `cost_cents`).

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

    biz_id = await _resolve_owned_business(ctx, args)
    if isinstance(biz_id, dict):
        return biz_id

    summary = _require_str(args, "summary")
    if isinstance(summary, dict):
        return summary

    kind = args.get("kind", "other")
    if kind not in _APPROVAL_KINDS:
        return {
            "status": "error",
            "summary": f"kind must be one of {list(_APPROVAL_KINDS)}",
        }

    expires_raw = args.get("expires_in_hours", 24)
    if isinstance(expires_raw, bool) or not isinstance(expires_raw, int) or expires_raw <= 0:
        return {"status": "error", "summary": "expires_in_hours must be a positive integer"}

    details = args.get("details")
    if details is not None and not isinstance(details, dict):
        return {"status": "error", "summary": "details must be an object if provided"}

    row = Approval(
        business_id=biz_id,
        kind=kind,
        summary=summary,
        details=details or {},
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(hours=expires_raw),
    )
    ctx.db.add(row)
    # Approval row + audit event must land or roll back together. Network
    # I/O (SSE emit, push) happens after commit and is best-effort.
    await ctx.db.flush()
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
        commit=False,
    )
    await ctx.db.commit()

    ctx.events_out.append(
        ChatEvent(
            "approval_requested",
            {
                "approval_id": str(row.id),
                "approval_kind": row.kind,
                "summary": row.summary,
                "details": row.details,
                "business_id": str(biz_id),
                "expires_at": row.expires_at.isoformat(),
            },
        )
    )

    # Fire push so a backgrounded phone buzzes. Best-effort; no-op when the
    # user hasn't registered a token yet.
    user_row = (
        await ctx.db.execute(select(User).where(User.id == ctx.user_id))
    ).scalar_one_or_none()
    if user_row is not None:
        amount_cents = row.details.get("amount_cents") if isinstance(row.details, dict) else None
        if isinstance(amount_cents, int) and amount_cents > 0:
            title = f"Approve ${amount_cents / 100:.0f}?"
        else:
            title = "Approval needed"
        await push.send_to_user(
            user_row.expo_push_token,
            title=title,
            body=row.summary[:160],
            data={
                "type": "approval_requested",
                "approval_id": str(row.id),
                "business_id": str(biz_id),
            },
        )

    return {
        "approval_id": str(row.id),
        "status": "pending",
        "expires_at": row.expires_at.isoformat(),
        "note": "Do not execute the proposed action until the user responds.",
    }


async def _create_business(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    name = args.get("name")
    vertical = args.get("vertical")
    if not isinstance(name, str) or not name.strip():
        return {"status": "error", "summary": "name is required"}
    if vertical not in _VERTICALS:
        return {
            "status": "error",
            "summary": f"vertical must be one of {sorted(_VERTICALS)}",
        }

    cap = int(args.get("weekly_spend_cap_cents", 50000))
    biz = Business(
        user_id=ctx.user_id,
        name=name.strip(),
        vertical=vertical,
        weekly_spend_cap_cents=cap,
        status="initializing",
    )
    ctx.db.add(biz)
    # Flush populates biz.id without committing, so the audit event lands
    # in the same transaction as the row it describes (CLAUDE.md rule #4).
    await ctx.db.flush()
    await event_log.write(
        ctx.db,
        session_id=ctx.session_id,
        business_id=biz.id,
        event_type="business_created",
        agent_name="ceo_agent",
        payload={
            "business_id": str(biz.id),
            "name": biz.name,
            "vertical": biz.vertical,
            "weekly_spend_cap_cents": biz.weekly_spend_cap_cents,
        },
        commit=False,
    )
    await ctx.db.commit()
    return {
        "status": "ok",
        "business_id": str(biz.id),
        "name": biz.name,
        "vertical": biz.vertical,
        "status_field": biz.status,
        "weekly_spend_cap_cents": biz.weekly_spend_cap_cents,
    }


async def _request_spend(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    biz = await _resolve_owned_business(ctx, args)
    if isinstance(biz, dict):
        return biz

    amount = args.get("amount_cents")
    if not isinstance(amount, int) or amount <= 0:
        return {"status": "error", "summary": "amount_cents must be a positive integer"}

    merchant = _require_str(args, "merchant_hint")
    if isinstance(merchant, dict):
        return merchant
    purpose = _require_str(args, "purpose")
    if isinstance(purpose, dict):
        return purpose

    logged = await event_log.write(
        ctx.db,
        session_id=ctx.session_id,
        business_id=biz,
        event_type="spend_intent",
        agent_name="ceo_agent",
        payload={
            "amount_cents": amount,
            "merchant_hint": merchant,
            "purpose": purpose,
        },
    )
    return {
        "status": "ok",
        "intent_id": logged.id,
        "amount_cents": amount,
        "note": (
            "Intent recorded. The actual charge goes through Stripe when the "
            "merchant submits the transaction; our authorization webhook will "
            "correlate on the merchant_hint + amount."
        ),
    }


async def _escalate_to_computer_use(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    biz = await _resolve_owned_business(ctx, args)
    if isinstance(biz, dict):
        return biz

    task = _require_str(args, "task")
    if isinstance(task, dict):
        return task
    app_hint = _require_str(args, "app_hint")
    if isinstance(app_hint, dict):
        return app_hint

    logged = await event_log.write(
        ctx.db,
        session_id=ctx.session_id,
        business_id=biz,
        event_type="computer_use_requested",
        agent_name="ceo_agent",
        payload={"task": task, "app_hint": app_hint},
    )
    return {
        "status": "queued",
        "escalation_id": logged.id,
        "note": (
            "Computer-use task queued. The desktop app picks this up when the "
            "user opens it. Tell the user to watch the screen when prompted."
        ),
    }


CEO_TOOL_IMPLS: dict[str, ToolFn] = {
    "get_current_time": _get_current_time,
    "query_event_log": _query_event_log,
    "delegate_to_specialist": _delegate_to_specialist,
    "request_user_approval": _request_user_approval,
    "create_business": _create_business,
    "escalate_to_computer_use": _escalate_to_computer_use,
    "request_spend": _request_spend,
}


def _summarize(payload: dict[str, Any]) -> str:
    if "text" in payload:
        text = str(payload["text"])
        return text[:200] + ("…" if len(text) > 200 else "")
    if "name" in payload:
        return f"{payload.get('name', '?')}({list(payload.get('input', {}).keys())})"
    return ", ".join(f"{k}={v}" for k, v in list(payload.items())[:3])

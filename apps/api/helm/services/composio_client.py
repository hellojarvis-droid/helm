"""Composio integration — the unified tool gateway.

Session 1 scope: the interface + tenant-id helper. The Composio v1.x SDK
surfaces `toolkits`, `tools`, `connected_accounts`, `auth_configs`, `mcp`,
and `triggers` namespaces — enough to implement `initiate_connection`,
`list_tools`, and `execute_tool`. Session 2 fills these in alongside the
first Composio-backed specialist.

Tenant scoping is already decided:
  Composio `user_id` = `f"{helm_user_id}::{business_id_or_orch}"`

Every agent-facing tool call routes through `execute_tool`; the runtime
wrapper enforces kill-switch + event-log invariants around it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from helm.config import get_settings

_ORCHESTRATOR_ENTITY_SUFFIX = "orch"


def entity_id_for(user_id: uuid.UUID, business_id: uuid.UUID | None) -> str:
    """Stable tenant identifier for Composio.

    `business_id=None` → orchestrator tools (not scoped to a single business).
    """
    if business_id is None:
        return f"{user_id}::{_ORCHESTRATOR_ENTITY_SUFFIX}"
    return f"{user_id}::{business_id}"


@dataclass(frozen=True, slots=True)
class ConnectionRequest:
    """Handed back to the client/UI so the user can complete OAuth."""

    redirect_url: str
    connection_id: str


def _platform_key() -> str:
    key = get_settings().composio_api_key
    if not key:
        raise RuntimeError("COMPOSIO_API_KEY is not configured")
    return key


async def initiate_connection(
    toolkit: str,
    user_id: uuid.UUID,
    business_id: uuid.UUID | None,
    callback_url: str | None = None,
) -> ConnectionRequest:
    """Kick off a Composio OAuth flow for the given toolkit.

    Session 1 is not yet wired against the SDK — returning a clear marker so
    a premature caller fails loudly instead of silently. Session 2 replaces
    the body with the real `auth_configs.initiate(...)` flow and persists the
    connection in the `integrations` table on the webhook callback.
    """
    _ = _platform_key()
    _ = entity_id_for(user_id, business_id)
    _ = (toolkit, callback_url)
    raise NotImplementedError(
        "initiate_connection lands in Phase 1 Session 2 with the first real toolkit wiring"
    )


async def list_tools(
    user_id: uuid.UUID,
    business_id: uuid.UUID | None,
    toolkits: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return the tool schemas Anthropic's Messages API accepts.

    When implemented, this will call Composio's `tools.get(..., format="anthropic")`
    scoped to our entity_id, and return the list verbatim.
    """
    _ = _platform_key()
    _ = entity_id_for(user_id, business_id)
    _ = toolkits
    raise NotImplementedError(
        "list_tools lands in Phase 1 Session 2 alongside delegate_to_specialist"
    )


async def execute_tool(
    tool_slug: str,
    arguments: dict[str, Any],
    user_id: uuid.UUID,
    business_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Execute a tool by slug with tenant-scoped auth.

    Caller contract (the runtime wrapper):
      - `kill_switch.assert_not_set` must be called BEFORE this.
      - `event_log.write` must be called with the result AFTER this.
    Enforcing those inside here would duplicate logic that belongs at the
    runtime level where all tool flavors (Composio + in-process + specialist-
    delegation) converge.
    """
    _ = _platform_key()
    _ = entity_id_for(user_id, business_id)
    _ = (tool_slug, arguments)
    raise NotImplementedError(
        "execute_tool lands in Phase 1 Session 2 once we have a Composio connection "
        "to exercise end-to-end"
    )

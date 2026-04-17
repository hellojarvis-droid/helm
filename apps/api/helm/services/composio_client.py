"""Composio integration — the unified tool gateway.

Session 4 ships the initiation + listing + execution surface we need for
OAuth. Per-tool conversion to Anthropic's `ToolParam` shape lands in Session 5
when the first specialist actually hands Composio tools to Claude.

Tenant scoping: Composio's `user_id` concept maps 1:1 to our entity_id
format `{helm_user_id}::{business_id|orch}`. A call without a
`business_id` is orchestrator-scoped — use it only for user-level tools.

Every call writes to Composio's platform API key; user OAuth flows redirect
through Composio's managed auth when possible.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, cast

from composio import Composio
from composio.core.models.connected_accounts import ConnectionRequest as ComposioConnReq

from helm.config import get_settings

_ORCHESTRATOR_ENTITY_SUFFIX = "orch"


def entity_id_for(user_id: uuid.UUID, business_id: uuid.UUID | None) -> str:
    """Stable tenant identifier for Composio."""
    if business_id is None:
        return f"{user_id}::{_ORCHESTRATOR_ENTITY_SUFFIX}"
    return f"{user_id}::{business_id}"


@dataclass(frozen=True, slots=True)
class ConnectionRequest:
    """Result of initiating an OAuth flow — handed to the client/UI."""

    connection_id: str
    redirect_url: str
    status: str  # Composio's own status, typically "INITIATED"


# The Composio class is generic over a provider type (Composio[TProvider]);
# we don't use a provider (we convert tool schemas to Anthropic format manually),
# so `Composio[Any, Any]` is the honest annotation.
_client: Composio[Any, Any] | None = None


def _get_client() -> Composio[Any, Any]:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.composio_api_key:
            raise RuntimeError("COMPOSIO_API_KEY is not configured")
        _client = Composio(api_key=settings.composio_api_key)
    return _client


async def initiate_connection(
    toolkit: str,
    user_id: uuid.UUID,
    business_id: uuid.UUID | None,
    callback_url: str | None = None,
) -> ConnectionRequest:
    """Kick off a Composio OAuth flow for the given toolkit.

    Returns a `ConnectionRequest` whose `redirect_url` the UI shows the user;
    they complete OAuth at Composio, which posts a `connection.complete` event
    to our `/webhooks/composio` — the handler flips our integrations row
    to `status='active'`.

    `toolkit` is a Composio toolkit slug, e.g. "gmail", "shopify", "meta_ads".
    If an auth config for this project+toolkit doesn't exist, Composio auto-
    creates a managed one (Composio maintains OAuth apps for common toolkits).
    """
    eid = entity_id_for(user_id, business_id)
    client = _get_client()

    def _authorize() -> ComposioConnReq:
        # Composio's high-level helper. Creates auth config + connection
        # request in one call; Composio handles callback_url registration
        # at the platform level for managed auth. The SDK's provider generic
        # erases return types to Any — cast to the concrete class.
        return cast(ComposioConnReq, client.toolkits.authorize(user_id=eid, toolkit=toolkit))

    conn = await _in_thread(_authorize)
    assert isinstance(conn, ComposioConnReq)
    if not conn.redirect_url:
        raise RuntimeError(
            f"Composio did not return a redirect URL for toolkit={toolkit!r}. "
            f"Ensure the toolkit is enabled in your Composio workspace."
        )
    return ConnectionRequest(
        connection_id=conn.id,
        redirect_url=conn.redirect_url,
        status=conn.status,
    )


async def get_connection(connection_id: str) -> dict[str, Any]:
    """Fetch a connection's current state (status, metadata) by Composio ID."""
    client = _get_client()

    def _fetch() -> Any:
        return client.connected_accounts.get(nanoid=connection_id)

    result = await _in_thread(_fetch)
    # The SDK returns a Pydantic-like object; dump to dict for DB persistence.
    if hasattr(result, "model_dump"):
        return dict(result.model_dump())
    if hasattr(result, "__dict__"):
        return dict(result.__dict__)
    return {"raw": str(result)}


async def list_tools(
    user_id: uuid.UUID,
    business_id: uuid.UUID | None,
    toolkits: list[str] | None = None,
) -> list[Any]:
    """Return tools available for this tenant in this toolkit selection.

    Session 4 returns the raw Composio Tool collection; Session 5 adds the
    `to_anthropic_tool_params(...)` transformer alongside the first
    specialist that delegates via Composio.
    """
    eid = entity_id_for(user_id, business_id)
    client = _get_client()

    def _get() -> Any:
        return client.tools.get(user_id=eid, toolkits=toolkits)

    return list(await _in_thread(_get))


async def execute_tool(
    tool_slug: str,
    arguments: dict[str, Any],
    user_id: uuid.UUID,
    business_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Execute a Composio tool on behalf of the tenant.

    The runtime wrapper is responsible for:
      - calling `kill_switch.assert_not_set` BEFORE this
      - calling `event_log.write` with the result AFTER this
    We deliberately don't hide either inside this function — the runtime
    keeps the enforcement in one place (see helm.agents.runtime).
    """
    eid = entity_id_for(user_id, business_id)
    client = _get_client()

    def _exec() -> Any:
        return client.tools.execute(tool_slug, arguments, user_id=eid)

    response = await _in_thread(_exec)
    if hasattr(response, "model_dump"):
        return dict(response.model_dump())
    return {"raw": str(response)}


async def _in_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Composio's SDK is synchronous; run blocking calls in the default executor
    so the event loop stays responsive."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

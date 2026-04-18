"""Langfuse LLM tracing — generations + metadata.

Every Anthropic call the CEO runtime and specialists make posts a
`generation` event to Langfuse when the three env vars are set
(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST). Missing config
silently degrades — we never block a chat turn on telemetry.

Traces attach session_id, business_id, user_id, agent_name, and token
counts so the Langfuse dashboard groups by user → session → turn → call.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from helm.config import get_settings

log = structlog.get_logger("helm.tracing")

_client: Any | None = None
_attempted_init = False


def _langfuse() -> Any | None:
    """Return the Langfuse client, or None if not configured.

    Lazily initialized on first call. A single shared client is fine —
    the SDK batches + flushes internally. On init failure we log once
    and never retry this process (Langfuse being down must not delay
    user-facing chat).
    """
    global _client, _attempted_init
    if _attempted_init:
        return _client

    _attempted_init = True
    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None

    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception as e:  # SDK import or init blew up — log + continue silent.
        log.warning("tracing.langfuse_init_failed", err=str(e)[:200])
        _client = None
    return _client


def record_generation(
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID | None,
    business_id: uuid.UUID | None,
    agent_name: str,
    model: str,
    input_messages: list[dict[str, Any]] | str,
    output_text: str,
    input_tokens: int,
    output_tokens: int,
    cost_cents: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Post a single LLM generation to Langfuse.

    Safe to call unconditionally — no-op when the client isn't configured.
    Never raises; Langfuse problems must not surface to the user.
    """
    client = _langfuse()
    if client is None:
        return

    try:
        client.generation(
            name=f"{agent_name}_turn",
            model=model,
            input=input_messages,
            output=output_text,
            usage={
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
                "unit": "TOKENS",
            },
            trace_id=str(session_id),
            metadata={
                "agent_name": agent_name,
                "user_id": str(user_id) if user_id else None,
                "business_id": str(business_id) if business_id else None,
                "cost_cents": cost_cents,
                **(metadata or {}),
            },
        )
    except Exception as e:
        log.warning("tracing.record_generation_failed", err=str(e)[:200])


def flush() -> None:
    """Flush pending events. Called at app shutdown."""
    client = _langfuse()
    if client is None:
        return
    try:
        client.flush()
    except Exception as e:
        log.warning("tracing.flush_failed", err=str(e)[:200])

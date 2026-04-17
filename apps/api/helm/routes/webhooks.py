"""Webhooks — incoming events from external services.

Composio: POSTs connection lifecycle events (created / expired / inactive).
We verify the HMAC-SHA256 signature in the `X-Composio-Signature-256` header
against `COMPOSIO_WEBHOOK_SECRET`, then flip the matching `integrations` row
to the new status.

Sig format assumption: `sha256=<hex>` over the raw request body. If the
dashboard surfaces a different scheme when the user wires webhooks, we
adjust here. Constant-time compare via `hmac.compare_digest`.

Unknown event types return 200 after logging — we never want Composio
retrying forever because of a shape change we haven't caught up with.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.config import get_settings
from helm.db.models import Integration
from helm.db.session import get_session

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = structlog.get_logger("helm.webhooks.composio")

_SIG_HEADER = "x-composio-signature-256"
_SIG_PREFIX = "sha256="


def _verify_composio_signature(body: bytes, signature_header: str | None) -> bool:
    """HMAC-SHA256 verification against COMPOSIO_WEBHOOK_SECRET.

    Returns False if no secret is configured (fail-closed) so we never
    accept unsigned events by accident. In dev you can set the secret to a
    known value and replay real Composio requests; in prod it comes from
    the Render env.
    """
    settings = get_settings()
    secret = settings.composio_webhook_secret
    if not secret or signature_header is None:
        return False
    if not signature_header.startswith(_SIG_PREFIX):
        return False
    expected_hex = signature_header[len(_SIG_PREFIX) :]
    computed = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, expected_hex)


def _status_from_event(event_type: str, payload: dict[str, Any]) -> str | None:
    """Return the integrations.status to set, or None to leave it alone."""
    # Composio event types follow `composio.<resource>.<action>`.
    if event_type.endswith(".expired"):
        return "expired"
    if event_type.endswith(".inactive") or event_type.endswith(".failed"):
        return "failed"
    # Connected/created/updated → look at the embedded status if present.
    data = payload.get("data") or payload.get("connected_account") or {}
    upstream_status = str(data.get("status", "")).upper()
    if upstream_status == "ACTIVE":
        return "active"
    if upstream_status == "FAILED":
        return "failed"
    if upstream_status == "EXPIRED":
        return "expired"
    return None


@router.post("/composio", status_code=status.HTTP_200_OK)
async def composio_webhook(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    body = await request.body()
    signature = request.headers.get(_SIG_HEADER)
    if not _verify_composio_signature(body, signature):
        log.warning(
            "webhook.bad_signature", has_secret=bool(get_settings().composio_webhook_secret)
        )
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        payload: dict[str, Any] = await request.json()
    except Exception as e:
        log.warning("webhook.bad_json", err=str(e))
        raise HTTPException(status_code=400, detail="invalid json") from e

    event_type = str(payload.get("type") or payload.get("event_type") or "unknown")
    connection_id = _extract_connection_id(payload)
    log.info("webhook.received", event_type=event_type, connection_id=connection_id)

    if connection_id is None:
        return {"status": "ignored", "reason": "no connection_id in payload"}

    new_status = _status_from_event(event_type, payload)
    if new_status is None:
        return {"status": "ignored", "reason": "no status mapping for event"}

    # Flip the matching integrations row. Idempotent: re-delivery hits the same row.
    res = await db.execute(
        select(Integration).where(Integration.composio_connection_id == connection_id)
    )
    row = res.scalar_one_or_none()
    if row is None:
        # Not our connection — could be another tenant on the same Composio
        # workspace. 200 OK so Composio doesn't retry.
        return {"status": "ignored", "reason": "unknown connection_id"}

    row.status = new_status
    row.meta = {
        **row.meta,
        "last_webhook_event": event_type,
        "last_webhook_status": new_status,
    }
    await db.commit()
    return {"status": "ok", "integration_status": new_status}


def _extract_connection_id(payload: dict[str, Any]) -> str | None:
    """Composio webhooks carry the connection id under varying keys depending
    on event type. Check a few plausible locations before giving up."""
    for key in ("connection_id", "connected_account_id", "nanoid", "id"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val
    data = payload.get("data") or payload.get("connected_account") or {}
    if isinstance(data, dict):
        for key in ("id", "connection_id", "nanoid"):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val
    return None

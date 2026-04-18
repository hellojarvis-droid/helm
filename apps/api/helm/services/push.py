"""Expo Push notifications — fire-and-forget async send.

Expo's push API (https://exp.host/--/api/v2/push/send) accepts a JSON body
with a list of messages. We talk directly rather than pulling the whole
expo-server-sdk — the shape is stable and a single POST keeps the dep
graph tight.

Send is best-effort: push being down should never block an approval
write. `send_to_user` schedules the POST and returns immediately —
failures log and swallow.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from helm.config import get_settings

log = structlog.get_logger("helm.push")

_EXPO_URL = "https://exp.host/--/api/v2/push/send"

# Hold task refs so the GC doesn't cancel in-flight fire-and-forget sends.
_pending: set[asyncio.Task[None]] = set()


async def send_to_user(
    expo_push_token: str | None,
    *,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Schedule a push to one Expo token. No-op if token is missing.

    Fire-and-forget: push being slow or failing must not block the caller.
    """
    if not expo_push_token:
        return
    task = asyncio.create_task(_send_one(expo_push_token, title, body, data or {}))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def _send_one(
    token: str,
    title: str,
    body: str,
    data: dict[str, Any],
) -> None:
    settings = get_settings()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    # Expo access token is only required for Enhanced Security mode; when set
    # we send it as a Bearer so the project-level token is honored.
    if settings.expo_access_token:
        headers["Authorization"] = f"Bearer {settings.expo_access_token}"

    payload = [
        {
            "to": token,
            "title": title,
            "body": body,
            "data": data,
            "sound": "default",
            "priority": "high",
        }
    ]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(_EXPO_URL, json=payload, headers=headers)
            if r.status_code >= 400:
                log.warning(
                    "push.expo_error",
                    status=r.status_code,
                    body=r.text[:300],
                )
                return
            # Expo returns per-message receipts — log any DeviceNotRegistered
            # so the caller can eventually drop the token.
            try:
                rj = r.json()
            except Exception:
                return
            if isinstance(rj.get("data"), list):
                for receipt in rj["data"]:
                    status = receipt.get("status")
                    if status != "ok":
                        log.warning(
                            "push.receipt_nonok",
                            status=status,
                            details=receipt.get("details"),
                            message=receipt.get("message"),
                        )
    except Exception as e:
        log.warning("push.send_failed", err=str(e)[:200])

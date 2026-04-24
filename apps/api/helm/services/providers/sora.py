"""Sora (OpenAI) — text-to-video with strong motion.

Sora's public API is gated behind OpenAI's `videos` endpoint. Adapter is
video-only. Works with the OpenAI API key; users who have Sora access on
their OpenAI org can plug their key in directly or use Helm's shared
account when enabled via env.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from helm.services.providers.base import ProviderJob, RenderMode

log = structlog.get_logger("helm.providers.sora")

_API_BASE = "https://api.openai.com/v1"


class SoraProvider:
    slug = "sora"
    supports_image = False
    supports_video = True

    async def start(
        self,
        *,
        mode: RenderMode,
        prompt: str,
        options: dict[str, Any],
        api_key: str,
    ) -> ProviderJob:
        if mode != "video":
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error="sora is video-only",
            )
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        duration = int(options.get("duration_seconds", 5))
        body: dict[str, Any] = {
            "model": options.get("model", "sora-2"),
            "prompt": prompt,
            "seconds": str(duration),
            "size": _size_for(options.get("aspect_ratio", "9:16")),
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{_API_BASE}/videos", headers=headers, json=body)
        if r.status_code >= 400:
            log.warning("sora.start_failed", status=r.status_code, body=r.text[:400])
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error=f"sora {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        job_id = payload.get("id")
        status = _map_status(payload.get("status"))
        return ProviderJob(
            external_job_id=str(job_id) if job_id else None,
            status=status,
        )

    async def poll(self, *, external_job_id: str, api_key: str) -> ProviderJob:
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{_API_BASE}/videos/{external_job_id}", headers=headers
            )
        if r.status_code >= 400:
            return ProviderJob(
                external_job_id=external_job_id,
                status="failed",
                error=f"sora poll {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        status = _map_status(payload.get("status"))
        return ProviderJob(
            external_job_id=external_job_id,
            status=status,
            output_url=_video_url(payload),
            error=(payload.get("error", {}) or {}).get("message")
            if status == "failed"
            else None,
        )

    def estimate_cost_cents(self, *, mode: RenderMode, options: dict[str, Any]) -> int:
        duration = int(options.get("duration_seconds", 5))
        return duration * 10


def _size_for(aspect: str) -> str:
    return {
        "9:16": "720x1280",
        "1:1": "1024x1024",
        "16:9": "1280x720",
        "4:5": "896x1120",
    }.get(aspect, "720x1280")


def _map_status(upstream: Any) -> str:
    v = str(upstream or "").lower()
    if v in {"completed", "succeeded"}:
        return "completed"
    if v in {"failed", "error"}:
        return "failed"
    if v in {"queued", "pending"}:
        return "queued"
    return "running"


def _video_url(payload: dict[str, Any]) -> str | None:
    # Sora responses vary — try a few shapes defensively.
    if payload.get("video_url"):
        return str(payload["video_url"])
    data = payload.get("data") or {}
    if isinstance(data, dict):
        return data.get("video_url")
    return None


SORA = SoraProvider()

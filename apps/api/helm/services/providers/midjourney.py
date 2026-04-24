"""Midjourney — aesthetic-leading image generation.

Midjourney doesn't have a public API yet — the industry workaround is to
talk to one of the third-party relay services (GoAPI, UseAPI, etc.).
Adapter is image-only and written against GoAPI's Midjourney endpoints;
swap the base URL if you point at a different relay.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from helm.services.providers.base import ProviderJob, RenderMode

log = structlog.get_logger("helm.providers.midjourney")

_API_BASE = "https://api.goapi.ai/api/v1/task"


class MidjourneyProvider:
    slug = "midjourney"
    supports_image = True
    supports_video = False

    async def start(
        self,
        *,
        mode: RenderMode,
        prompt: str,
        options: dict[str, Any],
        api_key: str,
    ) -> ProviderJob:
        if mode != "image":
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error="midjourney is image-only",
            )
        aspect = options.get("aspect_ratio", "1:1")
        # MJ-style prompt flags get appended to the prompt string.
        full_prompt = f"{prompt} --ar {aspect} --v {options.get('version', '6')}"
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        body: dict[str, Any] = {
            "model": "midjourney",
            "task_type": "imagine",
            "input": {"prompt": full_prompt},
            "config": {"service_mode": "public"},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(_API_BASE, headers=headers, json=body)
        if r.status_code >= 400:
            log.warning(
                "midjourney.start_failed", status=r.status_code, body=r.text[:400]
            )
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error=f"midjourney {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        task_id = (payload.get("data") or {}).get("task_id")
        return ProviderJob(
            external_job_id=str(task_id) if task_id else None,
            status="queued",
        )

    async def poll(self, *, external_job_id: str, api_key: str) -> ProviderJob:
        headers = {"X-API-Key": api_key}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{_API_BASE}/{external_job_id}", headers=headers)
        if r.status_code >= 400:
            return ProviderJob(
                external_job_id=external_job_id,
                status="failed",
                error=f"midjourney poll {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        data = payload.get("data") or {}
        status = str(data.get("status") or "").lower()
        if status in {"completed", "success"}:
            output = data.get("output") or {}
            return ProviderJob(
                external_job_id=external_job_id,
                status="completed",
                output_url=output.get("image_url"),
            )
        if status in {"failed", "error"}:
            return ProviderJob(
                external_job_id=external_job_id,
                status="failed",
                error=str(data.get("error") or "midjourney failed"),
            )
        return ProviderJob(external_job_id=external_job_id, status="running")

    def estimate_cost_cents(self, *, mode: RenderMode, options: dict[str, Any]) -> int:
        return 8


MIDJOURNEY = MidjourneyProvider()

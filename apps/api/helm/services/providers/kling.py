"""Kling (kling.ai / klingai.com) — video generation, lip-sync, image.

Kuaishou's Kling runs a REST API under `api.klingai.com`. Like
Higgsfield, exact field names drift; we keep the adapter small and
record errors so we can iterate when a user hits one.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from helm.services.providers.base import ProviderJob, RenderMode

log = structlog.get_logger("helm.providers.kling")

_API_BASE = "https://api.klingai.com"


class KlingProvider:
    slug = "kling"
    supports_image = True
    supports_video = True

    async def start(
        self,
        *,
        mode: RenderMode,
        prompt: str,
        options: dict[str, Any],
        api_key: str,
    ) -> ProviderJob:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if mode == "image":
            endpoint = f"{_API_BASE}/v1/images/generations"
            body: dict[str, Any] = {
                "model": options.get("model", "kling-v2"),
                "prompt": prompt,
                "aspect_ratio": options.get("ratio", "16:9"),
                "n": 1,
            }
        else:
            endpoint = f"{_API_BASE}/v1/videos/generations"
            body = {
                "model": options.get("model", "kling-v2-master"),
                "prompt": prompt,
                "duration": int(options.get("duration", 5)),
                "aspect_ratio": options.get("ratio", "16:9"),
                "mode": options.get("mode", "pro"),
            }
            if options.get("reference_image_url"):
                body["image"] = options["reference_image_url"]

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(endpoint, headers=headers, json=body)
        if r.status_code >= 400:
            log.warning("kling.start_failed", status=r.status_code, body=r.text[:400])
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error=f"kling {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        job_id = (
            payload.get("task_id")
            or payload.get("id")
            or (payload.get("data") or {}).get("task_id")
        )
        return ProviderJob(
            external_job_id=str(job_id) if job_id else None,
            status=_map_status(payload.get("task_status") or payload.get("status")),
        )

    async def poll(self, *, external_job_id: str, api_key: str) -> ProviderJob:
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{_API_BASE}/v1/tasks/{external_job_id}", headers=headers)
        if r.status_code >= 400:
            return ProviderJob(
                external_job_id=external_job_id,
                status="failed",
                error=f"kling poll {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        status = _map_status(payload.get("task_status") or payload.get("status"))
        data = payload.get("task_result") or payload.get("data") or {}
        output_url: str | None = None
        if isinstance(data, dict):
            videos = data.get("videos") or data.get("video")
            if isinstance(videos, list) and videos:
                output_url = str(videos[0].get("url") or videos[0])
            elif isinstance(videos, str):
                output_url = videos
            elif isinstance(data.get("url"), str):
                output_url = data["url"]
        return ProviderJob(
            external_job_id=external_job_id,
            status=status,
            output_url=output_url if status == "completed" else None,
            error=(payload.get("task_status_msg") if status == "failed" else None),
        )

    def estimate_cost_cents(self, *, mode: RenderMode, options: dict[str, Any]) -> int:
        if mode == "image":
            return 3
        return max(30, int(options.get("duration", 5)) * 8)


def _map_status(upstream: Any) -> str:
    v = str(upstream or "").lower()
    if v in {"succeed", "succeeded", "completed", "success"}:
        return "completed"
    if v in {"failed", "fail", "error", "cancelled", "canceled"}:
        return "failed"
    if v in {"submitted", "queued", "pending"}:
        return "queued"
    return "running"


KLING = KlingProvider()

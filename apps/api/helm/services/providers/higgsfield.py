"""Higgsfield (higgsfield.ai) — video generation with camera control.

Higgsfield publishes a REST API. Endpoint shape + response envelope
subject to change; when the user hits an error, our adapter records the
response body into `render_jobs.error` so we can iterate quickly.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from helm.services.providers.base import ProviderJob, RenderMode

log = structlog.get_logger("helm.providers.higgsfield")

_API_BASE = "https://api.higgsfield.ai"


class HiggsfieldProvider:
    slug = "higgsfield"
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
                error="higgsfield does not render still images",
            )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "prompt": prompt,
            "duration_seconds": int(options.get("duration", 5)),
            "aspect_ratio": options.get("ratio", "16:9"),
        }
        if options.get("reference_image_url"):
            body["reference_image_url"] = options["reference_image_url"]
        if options.get("camera_motion"):
            body["camera_motion"] = options["camera_motion"]

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{_API_BASE}/v1/videos", headers=headers, json=body)
        if r.status_code >= 400:
            log.warning("higgsfield.start_failed", status=r.status_code, body=r.text[:400])
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error=f"higgsfield {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        job_id = payload.get("id") or payload.get("job_id")
        return ProviderJob(
            external_job_id=str(job_id) if job_id else None,
            status=_map_status(payload.get("status")),
        )

    async def poll(self, *, external_job_id: str, api_key: str) -> ProviderJob:
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{_API_BASE}/v1/videos/{external_job_id}", headers=headers)
        if r.status_code >= 400:
            return ProviderJob(
                external_job_id=external_job_id,
                status="failed",
                error=f"higgsfield poll {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        status = _map_status(payload.get("status"))
        output_url = payload.get("video_url") or payload.get("output_url")
        return ProviderJob(
            external_job_id=external_job_id,
            status=status,
            output_url=output_url if status == "completed" else None,
            thumbnail_url=payload.get("thumbnail_url"),
            error=(payload.get("error") if status == "failed" else None),
        )

    def estimate_cost_cents(self, *, mode: RenderMode, options: dict[str, Any]) -> int:
        if mode != "video":
            return 0
        # ~$0.05/sec public pricing approximation, display-only.
        return max(25, int(options.get("duration", 5)) * 5)


def _map_status(upstream: Any) -> str:
    v = str(upstream or "").lower()
    if v in {"completed", "succeeded", "success", "done"}:
        return "completed"
    if v in {"failed", "cancelled", "canceled", "error"}:
        return "failed"
    if v in {"queued", "pending"}:
        return "queued"
    return "running"


HIGGSFIELD = HiggsfieldProvider()

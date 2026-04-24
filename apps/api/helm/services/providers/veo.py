"""Veo 3 (Google DeepMind, served via Vertex AI) — 1080p video generation.

Veo is called through Google's Vertex AI long-running operations API.
For now we accept a user-provided Vertex API key + project id in the
connection's metadata; the adapter constructs the right URL.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from helm.services.providers.base import ProviderJob, RenderMode

log = structlog.get_logger("helm.providers.veo")


class VeoProvider:
    slug = "veo"
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
                error="veo is video-only",
            )
        project = options.get("gcp_project")
        location = options.get("gcp_location", "us-central1")
        if not project:
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error="veo requires options.gcp_project (Vertex AI project id)",
            )
        url = (
            f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
            f"/locations/{location}/publishers/google/models/veo-3:predictLongRunning"
        )
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body: dict[str, Any] = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "durationSeconds": int(options.get("duration", 8)),
                "aspectRatio": options.get("ratio", "16:9"),
            },
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, headers=headers, json=body)
        if r.status_code >= 400:
            log.warning("veo.start_failed", status=r.status_code, body=r.text[:400])
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error=f"veo {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        op_name = payload.get("name")
        return ProviderJob(
            external_job_id=str(op_name) if op_name else None,
            status="queued",
        )

    async def poll(self, *, external_job_id: str, api_key: str) -> ProviderJob:
        # external_job_id is the full operation name — Vertex wants GET on it.
        url = f"https://us-central1-aiplatform.googleapis.com/v1/{external_job_id}"
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, headers=headers)
        if r.status_code >= 400:
            return ProviderJob(
                external_job_id=external_job_id,
                status="failed",
                error=f"veo poll {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        if not payload.get("done"):
            return ProviderJob(external_job_id=external_job_id, status="running")
        if payload.get("error"):
            return ProviderJob(
                external_job_id=external_job_id,
                status="failed",
                error=str(payload["error"].get("message", ""))[:300],
            )
        response = payload.get("response") or {}
        videos = (
            response.get("predictions", [{}])[0].get("videos")
            if response.get("predictions")
            else None
        )
        output_url: str | None = None
        if isinstance(videos, list) and videos:
            output_url = videos[0].get("uri") or videos[0].get("url")
        return ProviderJob(
            external_job_id=external_job_id,
            status="completed",
            output_url=output_url,
        )

    def estimate_cost_cents(self, *, mode: RenderMode, options: dict[str, Any]) -> int:
        if mode != "video":
            return 0
        # Public Vertex Veo pricing approximation, display-only.
        return max(100, int(options.get("duration", 8)) * 12)


VEO = VeoProvider()

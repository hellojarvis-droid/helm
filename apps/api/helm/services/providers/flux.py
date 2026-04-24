"""Flux (Black Forest Labs) — photorealistic image generation.

Reliable mid-complexity product and lifestyle imagery. Image-only.
Uses the Flux API via the BFL endpoint.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from helm.services.providers.base import ProviderJob, RenderMode

log = structlog.get_logger("helm.providers.flux")

_API_BASE = "https://api.bfl.ml"


class FluxProvider:
    slug = "flux"
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
                error="flux is image-only",
            )
        headers = {"X-Key": api_key, "Content-Type": "application/json"}
        width, height = _dimensions_for(options.get("aspect_ratio", "1:1"))
        body: dict[str, Any] = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "safety_tolerance": 2,
        }
        model = options.get("model", "flux-pro-1.1")
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{_API_BASE}/v1/{model}", headers=headers, json=body
            )
        if r.status_code >= 400:
            log.warning("flux.start_failed", status=r.status_code, body=r.text[:400])
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error=f"flux {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        job_id = payload.get("id")
        return ProviderJob(
            external_job_id=str(job_id) if job_id else None,
            status="queued",
        )

    async def poll(self, *, external_job_id: str, api_key: str) -> ProviderJob:
        headers = {"X-Key": api_key}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{_API_BASE}/v1/get_result",
                headers=headers,
                params={"id": external_job_id},
            )
        if r.status_code >= 400:
            return ProviderJob(
                external_job_id=external_job_id,
                status="failed",
                error=f"flux poll {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        status = str(payload.get("status") or "").lower()
        if status == "ready":
            result = payload.get("result") or {}
            return ProviderJob(
                external_job_id=external_job_id,
                status="completed",
                output_url=result.get("sample"),
            )
        if status in {"error", "failed"}:
            return ProviderJob(
                external_job_id=external_job_id,
                status="failed",
                error=str(payload.get("details") or "flux failed"),
            )
        return ProviderJob(external_job_id=external_job_id, status="running")

    def estimate_cost_cents(self, *, mode: RenderMode, options: dict[str, Any]) -> int:
        model = str(options.get("model", "flux-pro-1.1"))
        return 10 if model.startswith("flux-pro") else 4


def _dimensions_for(aspect: str) -> tuple[int, int]:
    return {
        "9:16": (720, 1280),
        "1:1": (1024, 1024),
        "16:9": (1280, 720),
        "4:5": (896, 1120),
    }.get(aspect, (1024, 1024))


FLUX = FluxProvider()

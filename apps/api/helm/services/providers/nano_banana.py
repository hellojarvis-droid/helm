"""Nano Banana — photorealistic image generation.

Product-shot-quality image gen. Adapter is image-only."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from helm.services.providers.base import ProviderJob, RenderMode

log = structlog.get_logger("helm.providers.nano_banana")

_API_BASE = "https://api.nanobanana.ai"


class NanoBananaProvider:
    slug = "nano_banana"
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
                error="nano_banana is image-only",
            )
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body: dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": options.get("ratio", "1:1"),
        }
        if options.get("reference_image_url"):
            body["reference_image"] = options["reference_image_url"]
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{_API_BASE}/v1/images", headers=headers, json=body)
        if r.status_code >= 400:
            log.warning("nano_banana.start_failed", status=r.status_code, body=r.text[:400])
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error=f"nano_banana {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        # Many image APIs return the URL inline on the start call. Fold that
        # into a one-shot completion to save the poller a round-trip.
        output_url = payload.get("image_url") or payload.get("url")
        if output_url:
            return ProviderJob(
                external_job_id=None,
                status="completed",
                output_url=str(output_url),
            )
        job_id = payload.get("id")
        return ProviderJob(
            external_job_id=str(job_id) if job_id else None,
            status=_map_status(payload.get("status")),
        )

    async def poll(self, *, external_job_id: str, api_key: str) -> ProviderJob:
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{_API_BASE}/v1/images/{external_job_id}", headers=headers)
        if r.status_code >= 400:
            return ProviderJob(
                external_job_id=external_job_id,
                status="failed",
                error=f"nano_banana poll {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        status = _map_status(payload.get("status"))
        return ProviderJob(
            external_job_id=external_job_id,
            status=status,
            output_url=payload.get("image_url") or payload.get("url"),
            error=(payload.get("error") if status == "failed" else None),
        )

    def estimate_cost_cents(self, *, mode: RenderMode, options: dict[str, Any]) -> int:
        return 2


def _map_status(upstream: Any) -> str:
    v = str(upstream or "").lower()
    if v in {"completed", "succeeded", "done"}:
        return "completed"
    if v in {"failed", "error"}:
        return "failed"
    if v in {"queued", "pending"}:
        return "queued"
    return "running"


NANO_BANANA = NanoBananaProvider()

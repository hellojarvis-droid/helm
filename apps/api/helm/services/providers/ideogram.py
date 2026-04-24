"""Ideogram — text-rendering image generation.

Best-in-class for images with crisp in-image typography — packaging
mockups, social cards with readable copy. Image-only.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from helm.services.providers.base import ProviderJob, RenderMode

log = structlog.get_logger("helm.providers.ideogram")

_API_BASE = "https://api.ideogram.ai"


class IdeogramProvider:
    slug = "ideogram"
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
                error="ideogram is image-only",
            )
        headers = {"Api-Key": api_key, "Content-Type": "application/json"}
        body: dict[str, Any] = {
            "image_request": {
                "prompt": prompt,
                "aspect_ratio": _map_aspect(options.get("aspect_ratio", "1:1")),
                "model": options.get("model", "V_2"),
                "magic_prompt_option": "AUTO",
            }
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{_API_BASE}/generate", headers=headers, json=body)
        if r.status_code >= 400:
            log.warning(
                "ideogram.start_failed", status=r.status_code, body=r.text[:400]
            )
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error=f"ideogram {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        data = (payload.get("data") or [{}])[0]
        url = data.get("url")
        if url:
            return ProviderJob(
                external_job_id=None, status="completed", output_url=str(url)
            )
        return ProviderJob(external_job_id=None, status="failed", error="no url in response")

    async def poll(self, *, external_job_id: str, api_key: str) -> ProviderJob:
        # Ideogram returns inline, so poll is unreachable in practice.
        return ProviderJob(external_job_id=external_job_id, status="completed")

    def estimate_cost_cents(self, *, mode: RenderMode, options: dict[str, Any]) -> int:
        return 8


def _map_aspect(aspect: str) -> str:
    return {
        "9:16": "ASPECT_9_16",
        "1:1": "ASPECT_1_1",
        "16:9": "ASPECT_16_9",
        "4:5": "ASPECT_4_5",
    }.get(aspect, "ASPECT_1_1")


IDEOGRAM = IdeogramProvider()

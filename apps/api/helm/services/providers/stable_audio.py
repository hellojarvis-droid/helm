"""Stability AI — Stable Audio 2 for music + SFX.

Short-form (up to 3 minutes) music and sound effects. Audio-only.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from helm.services.providers.base import ProviderJob, RenderMode

log = structlog.get_logger("helm.providers.stable_audio")

_API_BASE = "https://api.stability.ai"


class StableAudioProvider:
    slug = "stable_audio"
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
                error="stable_audio is audio-only (request mode=image)",
            )
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "audio/mpeg"}
        data = {
            "prompt": prompt,
            "duration": str(int(options.get("duration_seconds", 15))),
            "model": options.get("model", "stable-audio-2.0"),
            "output_format": "mp3",
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{_API_BASE}/v2beta/audio/stable-audio-2/text-to-audio",
                headers=headers,
                data=data,
            )
        if r.status_code >= 400:
            log.warning(
                "stable_audio.start_failed",
                status=r.status_code,
                body=r.text[:400],
            )
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error=f"stable_audio {r.status_code}: {r.text[:300]}",
            )
        # Response body is the audio bytes. Storage upload lands later.
        log.info("stable_audio.produced_audio", bytes=len(r.content))
        return ProviderJob(
            external_job_id=None,
            status="completed",
            output_url=None,
        )

    async def poll(self, *, external_job_id: str, api_key: str) -> ProviderJob:
        return ProviderJob(external_job_id=external_job_id, status="completed")

    def estimate_cost_cents(self, *, mode: RenderMode, options: dict[str, Any]) -> int:
        return 5


STABLE_AUDIO = StableAudioProvider()

"""Cartesia — fast, low-latency voice synthesis.

Alternative to ElevenLabs with better streaming. The render pipeline
treats "audio" as `mode=image` for now (a single file returned inline);
Voice Director can route VO generation to Cartesia for tone
flexibility.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from helm.services.providers.base import ProviderJob, RenderMode

log = structlog.get_logger("helm.providers.cartesia")

_API_BASE = "https://api.cartesia.ai"


class CartesiaProvider:
    slug = "cartesia"
    # Cartesia produces audio; the current render pipeline has no
    # dedicated audio mode so we expose it as `image` (file output) —
    # the Voice Director reads the resulting URL as an audio asset.
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
                error="cartesia is audio-only (request mode=image)",
            )
        headers = {
            "X-API-Key": api_key,
            "Cartesia-Version": "2024-11-13",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model_id": options.get("model", "sonic-english"),
            "transcript": prompt,
            "voice": {"mode": "id", "id": options.get("voice_id", "")},
            "output_format": {
                "container": "mp3",
                "encoding": "mp3",
                "sample_rate": 44100,
            },
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{_API_BASE}/tts/bytes", headers=headers, json=body
            )
        if r.status_code >= 400:
            log.warning(
                "cartesia.start_failed", status=r.status_code, body=r.text[:400]
            )
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error=f"cartesia {r.status_code}: {r.text[:300]}",
            )
        # The response body *is* the audio bytes — we'd normally hand
        # those off to storage and return the storage URL. Storage
        # upload lives in a later pass; for now we signal completion
        # with the raw byte size so the caller knows it succeeded.
        size_bytes = len(r.content)
        log.info("cartesia.produced_audio", bytes=size_bytes)
        return ProviderJob(
            external_job_id=None,
            status="completed",
            output_url=None,  # wire through supabase storage in the audio pass
        )

    async def poll(self, *, external_job_id: str, api_key: str) -> ProviderJob:
        return ProviderJob(external_job_id=external_job_id, status="completed")

    def estimate_cost_cents(self, *, mode: RenderMode, options: dict[str, Any]) -> int:
        return 2


CARTESIA = CartesiaProvider()

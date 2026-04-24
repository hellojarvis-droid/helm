"""Suno — text-to-music generation.

Generates original background music for ads. Uses Suno's public API
with the `generate` endpoint.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from helm.services.providers.base import ProviderJob, RenderMode

log = structlog.get_logger("helm.providers.suno")

_API_BASE = "https://api.suno.ai"


class SunoProvider:
    slug = "suno"
    supports_image = True  # audio file delivered as a URL
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
                error="suno is audio-only (request mode=image)",
            )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "prompt": prompt,
            "make_instrumental": options.get("instrumental", True),
            "model": options.get("model", "chirp-v4"),
            "wait_audio": False,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{_API_BASE}/api/generate", headers=headers, json=body
            )
        if r.status_code >= 400:
            log.warning("suno.start_failed", status=r.status_code, body=r.text[:400])
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error=f"suno {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        first = (payload if isinstance(payload, list) else [payload])[0] or {}
        job_id = first.get("id")
        return ProviderJob(
            external_job_id=str(job_id) if job_id else None,
            status="queued",
        )

    async def poll(self, *, external_job_id: str, api_key: str) -> ProviderJob:
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{_API_BASE}/api/get?ids={external_job_id}", headers=headers
            )
        if r.status_code >= 400:
            return ProviderJob(
                external_job_id=external_job_id,
                status="failed",
                error=f"suno poll {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        rows = payload if isinstance(payload, list) else [payload]
        row = rows[0] if rows else {}
        status = str(row.get("status") or "").lower()
        if status in {"complete", "streaming", "submitted_for_processing"}:
            audio_url = row.get("audio_url")
            if audio_url:
                return ProviderJob(
                    external_job_id=external_job_id,
                    status="completed",
                    output_url=str(audio_url),
                )
            return ProviderJob(
                external_job_id=external_job_id, status="running"
            )
        if status in {"failed", "error"}:
            return ProviderJob(
                external_job_id=external_job_id,
                status="failed",
                error=str(row.get("error") or "suno failed"),
            )
        return ProviderJob(external_job_id=external_job_id, status="running")

    def estimate_cost_cents(self, *, mode: RenderMode, options: dict[str, Any]) -> int:
        return 15  # Suno's ballpark for a single track.


SUNO = SunoProvider()

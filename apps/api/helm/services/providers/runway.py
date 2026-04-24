"""Runway (runwayml.com) — Gen-4 image + video.

Docs: https://docs.dev.runwayml.com/api
- POST /v1/text_to_image               — text-only image (sync-started,
                                         async-polled)
- POST /v1/image_to_video              — needs `promptImage`; this is the
                                         only video endpoint. Pure
                                         text-to-video is not supported
                                         on the public API.
- GET  /v1/tasks/{id}                  — poll a job by id

**Auto-seed for text-to-video:** when the caller asks for a video
without supplying `reference_image_url`, we generate a seed image via
`text_to_image` first (synchronously polling until it completes), then
launch `image_to_video` with that image as `promptImage`. The returned
ProviderJob wraps the video task id so the Creative-Studio poller only
sees one job to follow; the seed is an implementation detail.

Status mapping from their envelope.status:
  PENDING, RUNNING, THROTTLED → running
  SUCCEEDED                   → completed
  FAILED, CANCELED            → failed
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from helm.services.providers.base import ProviderJob, RenderMode

log = structlog.get_logger("helm.providers.runway")

_API_BASE = "https://api.dev.runwayml.com"
_API_VERSION = "2024-11-06"

# How long we're willing to wait for the auto-seed image before giving up
# and returning a failure to the caller. ~60s is safe — Gen-4 image
# typically lands in 5-15s.
_SEED_POLL_TIMEOUT_S = 60
_SEED_POLL_INTERVAL_S = 2


class RunwayProvider:
    slug = "runway"
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
        headers = _headers(api_key)
        if mode == "image":
            return await self._start_text_to_image(prompt, options, headers)

        # Video: need a promptImage. Use the provided reference_image_url
        # when present, otherwise generate one on the fly.
        ref = options.get("reference_image_url")
        if not ref:
            seed_url, seed_error = await self._autoseed(prompt, options, headers)
            if seed_error is not None:
                return ProviderJob(
                    external_job_id=None,
                    status="failed",
                    error=seed_error,
                )
            ref = seed_url
        return await self._start_image_to_video(prompt, str(ref), options, headers)

    async def poll(self, *, external_job_id: str, api_key: str) -> ProviderJob:
        headers = _headers(api_key)
        url = f"{_API_BASE}/v1/tasks/{external_job_id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, headers=headers)
        if r.status_code >= 400:
            return ProviderJob(
                external_job_id=external_job_id,
                status="failed",
                error=f"runway poll {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        return _envelope_to_job(external_job_id, payload)

    def estimate_cost_cents(self, *, mode: RenderMode, options: dict[str, Any]) -> int:
        if mode == "image":
            return 5
        # Public approximation for gen4_turbo @ 720p: ~5¢/sec. When we
        # auto-seed, add the seed image's ~5¢ to the estimate so the UI
        # doesn't under-promise.
        duration = int(options.get("duration", 5))
        base = max(25, duration * 5)
        if not options.get("reference_image_url"):
            base += 5
        return base

    # ────────────────────────────────────────────────────────────────
    # Internals
    # ────────────────────────────────────────────────────────────────

    async def _start_text_to_image(
        self, prompt: str, options: dict[str, Any], headers: dict[str, str]
    ) -> ProviderJob:
        body = _image_body(prompt, options)
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{_API_BASE}/v1/text_to_image", headers=headers, json=body)
        if r.status_code >= 400:
            log.warning("runway.image_start_failed", status=r.status_code, body=r.text[:400])
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error=f"runway image {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        task_id = payload.get("id")
        return ProviderJob(
            external_job_id=str(task_id) if task_id else None,
            status=_map_status(payload.get("status")),
        )

    async def _start_image_to_video(
        self, prompt: str, prompt_image: str, options: dict[str, Any], headers: dict[str, str]
    ) -> ProviderJob:
        body = _video_body(prompt, prompt_image, options)
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{_API_BASE}/v1/image_to_video", headers=headers, json=body)
        if r.status_code >= 400:
            log.warning("runway.video_start_failed", status=r.status_code, body=r.text[:400])
            return ProviderJob(
                external_job_id=None,
                status="failed",
                error=f"runway video {r.status_code}: {r.text[:300]}",
            )
        payload = r.json()
        task_id = payload.get("id")
        return ProviderJob(
            external_job_id=str(task_id) if task_id else None,
            status=_map_status(payload.get("status")),
        )

    async def _autoseed(
        self, prompt: str, options: dict[str, Any], headers: dict[str, str]
    ) -> tuple[str | None, str | None]:
        """Generate a seed image synchronously, poll until it's ready,
        return (seed_url, None) on success or (None, error) on failure.

        Blocks for up to _SEED_POLL_TIMEOUT_S. The parent POST /renders
        call awaits this, so the request takes that long before the job
        shows up in the queue — acceptable for the "one prompt → one
        video" UX."""
        seed_options = {"ratio": options.get("ratio", "1280:720")}
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{_API_BASE}/v1/text_to_image",
                headers=headers,
                json=_image_body(prompt, seed_options),
            )
        if r.status_code >= 400:
            return None, f"runway seed image {r.status_code}: {r.text[:300]}"
        task_id = r.json().get("id")
        if not task_id:
            return None, "runway seed image: no task id returned"

        # Poll the seed until terminal.
        deadline = asyncio.get_running_loop().time() + _SEED_POLL_TIMEOUT_S
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(_SEED_POLL_INTERVAL_S)
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(f"{_API_BASE}/v1/tasks/{task_id}", headers=headers)
            if r.status_code >= 400:
                return None, f"runway seed poll {r.status_code}: {r.text[:200]}"
            job = _envelope_to_job(str(task_id), r.json())
            if job.status == "completed" and job.output_url:
                return job.output_url, None
            if job.status == "failed":
                return None, job.error or "runway seed image failed"
        return None, "runway seed image timed out"


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "X-Runway-Version": _API_VERSION,
        "Content-Type": "application/json",
    }


def _image_body(prompt: str, options: dict[str, Any]) -> dict[str, Any]:
    # Belt-and-suspenders: strip on-screen-text instructions even if the
    # upstream prompt still contains them. Runway's gen4_image is
    # strict about in-image typography and can reject these prompts.
    cleaned = _strip_text_overlay_instructions(prompt)
    return {
        "promptText": cleaned,
        "model": options.get("model", "gen4_image"),
        "ratio": options.get("ratio", "1280:720"),
    }


def _video_body(
    prompt: str, prompt_image: str, options: dict[str, Any]
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "promptText": prompt,
        "promptImage": prompt_image,
        "model": options.get("model", "gen4_turbo"),
        "duration": int(options.get("duration", 5)),
        "ratio": options.get("ratio", "1280:720"),
    }
    return body


def _envelope_to_job(job_id: str, payload: dict[str, Any]) -> ProviderJob:
    status = _map_status(payload.get("status"))
    output_url: str | None = None
    output = payload.get("output")
    if isinstance(output, list) and output:
        output_url = str(output[0])
    elif isinstance(output, str):
        output_url = output
    err: str | None = None
    if status == "failed":
        # Runway uses several fields across endpoints: failureReason
        # (camelCase on /tasks/{id}), failure_reason (snake elsewhere),
        # a nested {"error": "..."}, or just error. Fall back to the raw
        # payload so we don't silently drop the reason.
        raw = (
            payload.get("failureReason")
            or payload.get("failure_reason")
            or payload.get("failureCode")
            or payload.get("error")
        )
        if raw is None:
            raw = str(payload)[:400]
        err = str(raw)
    return ProviderJob(
        external_job_id=job_id,
        status=status,
        output_url=output_url if status == "completed" else None,
        error=err,
    )


def _strip_text_overlay_instructions(prompt: str) -> str:
    """Remove sentences that ask the model to render on-screen text.
    We composite text overlays in post; asking the image model to draw
    them is unreliable and sometimes rejected outright."""
    import re

    # Split into sentences on common terminators, drop any that mention
    # typography / text overlay patterns, then re-join.
    sentences = re.split(r"(?<=[.!?])\s+", prompt)
    skip_markers = (
        "on-screen text",
        "on screen text",
        "overlays lower third",
        "text overlay",
        "caption overlay",
    )
    kept = [
        s for s in sentences
        if not any(m in s.lower() for m in skip_markers)
    ]
    return " ".join(kept).strip() or prompt


def _map_status(upstream: Any) -> str:
    value = str(upstream or "").upper()
    if value in {"SUCCEEDED", "SUCCESS"}:
        return "completed"
    if value in {"FAILED", "CANCELED", "CANCELLED"}:
        return "failed"
    if value in {"PENDING", "THROTTLED"}:
        return "queued"
    return "running"


RUNWAY = RunwayProvider()

"""Ad importer — ingest an existing MP4/image into the Library.

The user pastes a URL (or uploads to storage first and pastes the
storage URL) and Helm reverse-engineers enough metadata to treat the
ad as a first-class Master Creative:

  1. Optionally transcribe the audio with Whisper (when
     `settings.openai_api_key` is set). Transcript becomes the VO script.
  2. Ask Claude Sonnet to draft a Creative Brief from the title +
     description + transcript. Even a rough brief lets Distributor +
     reformat + pattern-learning participate.
  3. Persist as `master_creatives.imported=true` with
     `canonical_output_url` pointing to the uploaded asset. No Shot rows
     are created — the asset is already rendered.

Credits: Whisper + Claude both flow through `services.credits` with
reserve→commit so imports count toward the usage budget.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import anthropic
import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from helm.config import get_settings
from helm.db.models import CreativeBrief, MasterCreative
from helm.services import credits
from helm.services.integration_vault import ProviderKeyMissingError

log = structlog.get_logger("helm.ad_importer")

_IMPORT_MAX_TOKENS = 1600

# Token prices must stay aligned with services/specialists/_llm.py.
_PRICES_CENTS = {
    "claude-sonnet-4-6": (300, 1500),
    "claude-opus-4-7": (1500, 7500),
    "claude-haiku-4-5-20251001": (25, 125),
}

# Rough budget so reserve has headroom. Whisper ~1¢ per minute; Claude
# brief ~2¢. 5¢ reservation with 20% headroom covers typical imports.
_IMPORT_ESTIMATE_CENTS = 5


class ImportFailedError(Exception):
    """Importer couldn't produce a usable brief. Caller converts to 502."""


_IMPORT_SYSTEM_PROMPT = """You are reverse-engineering a Creative Brief
from an existing ad a user is importing into their Library. The user
pastes a URL, maybe a description, and optionally a VO transcript.

Output a SINGLE JSON object, no prose, no fences:

{
  "title": "<short title for the Library>",
  "angles": [
    {"label": "<2-4 words>", "thesis": "<one sentence>"}
  ],
  "chosen_angle": "<label from angles>",
  "hook": "<first 3 seconds>",
  "narrative_arc": "<story structure>",
  "tone_descriptors": ["<three words>"],
  "headline": "<short on-brand headline>",
  "subhead": "<supporting sentence>",
  "cta": "<specific CTA>",
  "caption_meta": "<caption the user could use on IG/Facebook>",
  "caption_tiktok": "<TikTok version>",
  "tags": ["<4-6 searchable tags>"]
}

Rules:
- If transcript is empty, infer tone from the title/description only.
- Produce ONE angle if the provided info doesn't support three.
- Keep headline under 8 words.
- Output ONLY the JSON object. No markdown, no fences, no trailing text.
"""


async def import_existing(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    business_id: uuid.UUID,
    campaign_id: uuid.UUID,
    video_url: str,
    title: str,
    description: str | None,
    aspect_ratio: str,
    transcribe: bool = True,
) -> MasterCreative:
    """Create a MasterCreative from an existing ad asset."""
    reservation_id, _ = await credits.reserve(
        db,
        user_id=user_id,
        estimate_cents=_IMPORT_ESTIMATE_CENTS,
        reference_type="ad_import",
        description=f"Import reserved for {title}",
        meta={"business_id": str(business_id), "url": video_url},
    )
    await db.commit()

    transcript = ""
    if transcribe:
        try:
            transcript = await _whisper_transcribe(video_url)
        except Exception as e:
            # Transcription is best-effort — import still proceeds
            # without it, just using title+description for the brief.
            log.warning("ad_importer.transcribe_failed", err=str(e)[:200])

    settings = get_settings()
    if not settings.anthropic_api_key:
        await credits.refund(
            db,
            user_id=user_id,
            reservation_id=reservation_id,
            reason="anthropic not configured",
        )
        await db.commit()
        raise ProviderKeyMissingError("anthropic")

    user_message = json.dumps(
        {
            "title": title,
            "description": description or "",
            "transcript": transcript,
            "aspect_ratio": aspect_ratio,
            "video_url": video_url,
        },
        indent=2,
    )

    model = settings.specialist_model
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        msg = await client.messages.create(
            model=model,
            max_tokens=_IMPORT_MAX_TOKENS,
            system=_IMPORT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as e:
        await credits.refund(
            db,
            user_id=user_id,
            reservation_id=reservation_id,
            reason=f"anthropic error: {str(e)[:120]}",
        )
        await db.commit()
        raise ImportFailedError(f"anthropic api error: {e}") from e

    # Commit the actual cost.
    in_tokens = msg.usage.input_tokens
    out_tokens = msg.usage.output_tokens
    in_per_m, out_per_m = _PRICES_CENTS.get(model, (300, 1500))
    base_cents = (in_tokens * in_per_m + out_tokens * out_per_m) / 1_000_000
    actual_cents = max(1, int(base_cents * 1.01 + 0.999))
    await credits.commit(
        db,
        user_id=user_id,
        reservation_id=reservation_id,
        actual_cents=actual_cents,
        description=f"Ad import · {title}",
        meta={
            "model": model,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
        },
    )
    await db.commit()

    text = "".join(
        getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text"
    )
    parsed = _extract_json_object(text)
    if not parsed:
        raise ImportFailedError(
            f"model returned unparseable JSON (first 200 chars): {text[:200]}"
        )

    # Persist the Brief first so the creative can reference it.
    brief = CreativeBrief(
        campaign_id=campaign_id,
        version=await _next_version(db, campaign_id=campaign_id),
        user_input=description or "",
        angles=list(parsed.get("angles") or []),
        chosen_angle=parsed.get("chosen_angle"),
        hook=parsed.get("hook"),
        narrative_arc=parsed.get("narrative_arc"),
        tone_descriptors=list(parsed.get("tone_descriptors") or []),
        forbidden_territory=[],
        task_packets={},
        learnings={"imported": True, "source_url": video_url},
    )
    db.add(brief)
    await db.flush()

    creative = MasterCreative(
        campaign_id=campaign_id,
        brief_id=brief.id,
        title=parsed.get("title") or title,
        canonical_aspect=aspect_ratio,
        status="ready",
        copy={
            "copy": {
                "headline": parsed.get("headline"),
                "subhead": parsed.get("subhead"),
                "cta": parsed.get("cta"),
                "caption_meta": parsed.get("caption_meta"),
                "caption_tiktok": parsed.get("caption_tiktok"),
                "vo_script": [{"shot": 1, "line": transcript}] if transcript else [],
            }
        },
        canonical_output_url=video_url,
        imported=True,
        tags=list(parsed.get("tags") or []),
    )
    db.add(creative)
    await db.flush()
    return creative


async def _next_version(
    db: AsyncSession, *, campaign_id: uuid.UUID
) -> int:
    from sqlalchemy import select

    q = await db.execute(
        select(CreativeBrief.version)
        .where(CreativeBrief.campaign_id == campaign_id)
        .order_by(CreativeBrief.version.desc())
        .limit(1)
    )
    latest = q.scalar_one_or_none()
    return (latest or 0) + 1


async def _whisper_transcribe(video_url: str) -> str:
    """Download the video's audio and ship to OpenAI Whisper.

    Returns empty string when `openai_api_key` is not configured or the
    download/transcribe fails — import still works without audio.
    """
    settings = get_settings()
    openai_key = getattr(settings, "openai_api_key", None)
    if not openai_key:
        return ""

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        r = await client.get(video_url)
        r.raise_for_status()
        audio_bytes = r.content

    # Cap upload size — Whisper is 25MB per file. If over, skip rather
    # than corrupt the payload.
    if len(audio_bytes) > 24_000_000:
        log.warning("ad_importer.audio_too_large", size=len(audio_bytes))
        return ""

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {openai_key}"},
            files={"file": ("audio.mp4", audio_bytes, "audio/mp4")},
            data={"model": "whisper-1", "response_format": "text"},
        )
    if resp.status_code >= 400:
        log.warning(
            "ad_importer.whisper_failed",
            status=resp.status_code,
            body=resp.text[:200],
        )
        return ""
    return resp.text.strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    start = text.find("{")
    if start < 0:
        return {}
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start : i + 1])
                    return obj if isinstance(obj, dict) else {}
                except Exception:
                    return {}
    return {}

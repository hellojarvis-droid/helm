"""Brand Library — CRUD + URL-scrape population.

The Library is a first-class object per business: palette, typography,
logos, voice, banned phrases, winning references. It feeds every
downstream specialist (Copywriter pulls voice + banned-phrases; Art
Director pulls palette + typography; Editor pulls logo positioning).

URL-in onboarding (Phase 2 of the Creative Studio revamp) is the
primary population path. User pastes a website; we fetch, extract key
signals from the HTML, and ask Claude Sonnet to extract structured
brand attributes. The user then reviews + edits in the UI before
anything downstream consumes it.

Credits: the URL-scrape LLM call debits the user's credit balance via
`services/credits.reserve` → `commit` — typical cost is ~3¢ on a
small-to-medium site, silent (under the 10¢ inline-prompt threshold).
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import anthropic
import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.config import get_settings
from helm.db.models import BrandLibrary
from helm.services import credits
from helm.services.integration_vault import ProviderKeyMissingError

log = structlog.get_logger("helm.brand_library")

# Max tokens for the URL-scrape call. The model is config-driven
# (HELM_SPECIALIST_MODEL) so a flip to Haiku for cost or Opus for
# quality applies uniformly across every specialist call.
_SCRAPE_MAX_TOKENS = 1800

# Rough cost per scrape at this model + token budget. The reserve uses
# this as its estimate; the committed amount is the real usage from the
# response (with a ~1% markup per the billing decisions memo).
_SCRAPE_ESTIMATE_CENTS = 5

# How much of the page we keep before sending to Claude. HTML from
# real sites bloats fast — strip to text, cap at this character count,
# and let the model do the work.
_MAX_PAGE_CHARS = 24_000


class BrandScrapeFailedError(Exception):
    """URL fetch or LLM scrape failed. Route converts to 502."""


# ────────────────────────────────────────────────────────────────────
# Scrape
# ────────────────────────────────────────────────────────────────────


_SCRAPE_SYSTEM_PROMPT = """You extract structured brand attributes from a website.
The user will paste cleaned text from a single URL. Return a SINGLE JSON object
with this exact shape, no prose, no fences:

{
  "name": "<brand name as the site presents it>",
  "tagline": "<one-sentence promise, or null>",
  "palette": {
    "primary": "#RRGGBB",
    "secondary": "#RRGGBB",
    "accent": "#RRGGBB",
    "neutral": "#RRGGBB"
  },
  "typography": {
    "display": "<Google-Fonts-available font name, or null>",
    "body": "<Google-Fonts-available font name, or null>"
  },
  "voice_paragraph": "<one paragraph describing tone + sentence length + vocabulary level>",
  "tone_descriptors": ["<three words that capture the voice>", "...", "..."],
  "moodboard_keywords": ["<4-6 visual keywords>", "..."],
  "category_signals": ["<3-5 product / industry hints from the page>"]
}

Rules:
- Never invent hex codes. If you can't infer a value with confidence, return
  "#000000" for that slot and add a note to voice_paragraph ("palette inferred").
- Typography fonts MUST be Google-Fonts-available names. If the site uses a
  custom license-locked font (Helvetica Neue, Gotham, etc.), suggest the
  closest Google Fonts equivalent.
- Keep the voice_paragraph under 60 words. Lead with the register
  (intimate / direct / playful / authoritative).
- Output ONLY the JSON object. No markdown, no fences, no trailing text.
"""


async def scrape_url(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    business_id: uuid.UUID,
    url: str,
) -> dict[str, Any]:
    """Fetch a URL, extract key text, call Claude to produce a structured
    brand kit, and return the parsed dict.

    Debits the user's credit balance for the LLM call. Raises
    `BrandScrapeFailedError` on any step; route converts to 502.
    Raises `credits.InsufficientCreditsError` if the balance can't
    cover the reserve.
    """
    # 1. Reserve credits BEFORE the network + LLM work. If the user
    # can't afford it we fail fast with 402.
    reservation_id, _ = await credits.reserve(
        db,
        user_id=user_id,
        estimate_cents=_SCRAPE_ESTIMATE_CENTS,
        reference_type="brand_scrape",
        description=f"Brand scrape reserved for {url}",
        meta={"business_id": str(business_id), "url": url},
    )
    await db.commit()

    try:
        page_text = await _fetch_page_text(url)
    except Exception as e:
        await credits.refund(
            db,
            user_id=user_id,
            reservation_id=reservation_id,
            reason=f"fetch failed: {str(e)[:120]}",
        )
        await db.commit()
        raise BrandScrapeFailedError(f"fetch failed: {e}") from e

    # 2. LLM extract.
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

    model = settings.specialist_model
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        msg = await client.messages.create(
            model=model,
            max_tokens=_SCRAPE_MAX_TOKENS,
            system=_SCRAPE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"URL: {url}\n\n{page_text}"}],
        )
    except anthropic.APIError as e:
        await credits.refund(
            db,
            user_id=user_id,
            reservation_id=reservation_id,
            reason=f"anthropic api error: {str(e)[:120]}",
        )
        await db.commit()
        raise BrandScrapeFailedError(f"anthropic api error: {e}") from e

    # 3. Commit the actual cost (input + output tokens → cents with 1% markup).
    in_tokens = msg.usage.input_tokens
    out_tokens = msg.usage.output_tokens
    actual_cents = _cost_cents(model, in_tokens, out_tokens)
    await credits.commit(
        db,
        user_id=user_id,
        reservation_id=reservation_id,
        actual_cents=actual_cents,
        description=f"Brand scrape · {url}",
        meta={
            "model": model,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
        },
    )
    await db.commit()

    # 4. Parse the JSON response.
    text = "".join(
        getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text"
    )
    parsed = _extract_json_object(text)
    if not parsed:
        raise BrandScrapeFailedError(
            f"model returned unparseable JSON (first 200 chars): {text[:200]}"
        )
    return parsed


async def _fetch_page_text(url: str) -> str:
    """Fetch a URL's HTML and reduce to text content the LLM can reason
    about. Strip <script>/<style>, collapse whitespace, cap length."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; HelmBot/1.0; "
            "+https://helm.app/bot)"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    async with httpx.AsyncClient(
        timeout=10.0,
        follow_redirects=True,
        headers=headers,
    ) as client:
        r = await client.get(url)
    r.raise_for_status()
    html = r.text

    # Pull <title>, meta description, og:* tags first — these are the
    # highest-signal brand hints. Then strip the rest down to text.
    title = _first_match(r"<title[^>]*>([^<]+)</title>", html)
    meta_description = _first_match(
        r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)', html
    )
    og_title = _first_match(
        r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)', html
    )
    og_description = _first_match(
        r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)', html
    )

    # Drop script/style content entirely — they're noise for a brand
    # extraction and can be huge.
    body = re.sub(
        r"<(script|style|noscript)[^>]*>.*?</\1>",
        " ",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()

    return (
        f"TITLE: {title or '(no title tag)'}\n"
        f"META DESCRIPTION: {meta_description or '(none)'}\n"
        f"OG TITLE: {og_title or '(none)'}\n"
        f"OG DESCRIPTION: {og_description or '(none)'}\n\n"
        f"PAGE TEXT:\n{body[:_MAX_PAGE_CHARS]}"
    )


def _first_match(pattern: str, s: str) -> str | None:
    m = re.search(pattern, s, re.IGNORECASE | re.DOTALL)
    if m is None:
        return None
    return m.group(1).strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    """Best-effort: pull the first JSON object out of the model's text
    response. Returns {} on failure so callers can surface a clean error."""
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


# Per-1M-token prices in cents, aligned with services/specialists/_llm.py.
# Keep in lockstep — if we diverge the specialist billing and scrape
# billing won't match.
_PRICES_CENTS = {
    "claude-sonnet-4-6": (300, 1500),
    "claude-opus-4-7": (1500, 7500),
    "claude-haiku-4-5-20251001": (25, 125),
}


def _cost_cents(model: str, input_tokens: int, output_tokens: int) -> int:
    """1% markup per the billing decisions memo. Round up so we never
    under-charge."""
    in_cents_per_m, out_cents_per_m = _PRICES_CENTS.get(model, (300, 1500))
    base_cents = (input_tokens * in_cents_per_m + output_tokens * out_cents_per_m) / 1_000_000
    with_markup = base_cents * 1.01
    return max(1, int(with_markup + 0.999))


# ────────────────────────────────────────────────────────────────────
# CRUD helpers
# ────────────────────────────────────────────────────────────────────


async def get_for_business(
    db: AsyncSession, *, business_id: uuid.UUID
) -> BrandLibrary | None:
    row_q = await db.execute(
        select(BrandLibrary).where(BrandLibrary.business_id == business_id)
    )
    return row_q.scalar_one_or_none()


async def upsert(
    db: AsyncSession,
    *,
    business_id: uuid.UUID,
    fields: dict[str, Any],
) -> BrandLibrary:
    """Insert or update the business's brand library row with the given
    fields. Only keys that map to real columns are applied — extras
    are dropped to keep API payloads forgiving."""
    existing = await get_for_business(db, business_id=business_id)
    allowed = {
        "name",
        "tagline",
        "source_url",
        "palette",
        "typography",
        "logos",
        "voice_paragraph",
        "banned_phrases",
        "winning_references",
        "moodboard_urls",
    }
    filtered = {k: v for k, v in fields.items() if k in allowed and v is not None}

    if existing is None:
        # `name` is required on insert. Pull from the passed fields or
        # fall back to an empty string; callers are expected to set one.
        row = BrandLibrary(
            business_id=business_id,
            name=filtered.pop("name", ""),
            **filtered,
        )
        db.add(row)
    else:
        row = existing
        for k, v in filtered.items():
            setattr(row, k, v)
    await db.flush()
    return row

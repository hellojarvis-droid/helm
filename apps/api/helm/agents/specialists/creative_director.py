"""Creative Director — brand kit generation (text-only for Session 3).

Single-shot Sonnet 4.6 call: given a business concept + constraints, returns
a JSON brand kit (palette, typography, voice, logo concept). The result is
persisted to `businesses.brand_kit` JSONB by the caller (via `create_business`
or a follow-up update). Image generation arrives once the image-gen pipeline
is wired.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from helm.agents.specialists.base import (
    BusinessContext,
    LLMSpecialist,
    SpecialistResult,
    register,
)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "creative_director.md"

_JSON_BLOCK_RE = re.compile(r"```json\s*(?P<body>\{[\s\S]*?\})\s*```", re.MULTILINE)


class CreativeDirectorSpecialist(LLMSpecialist):
    """Wraps the base LLMSpecialist with structured brand-kit parsing.

    The model is instructed to return a single ```json block; we parse it and
    expose the parsed dict as `metadata['brand_kit']` in the SpecialistResult.
    Falls back to `status='error'` if the model drifted and we couldn't parse.
    """

    def __init__(self) -> None:
        super().__init__(
            name="creative_director",
            model="claude-sonnet-4-6",
            system_prompt=_PROMPT_PATH.read_text(),
            tools=[],
            max_tokens=2500,
        )

    async def run(
        self,
        db: AsyncSession,
        ctx: BusinessContext,
        task: str,
    ) -> SpecialistResult:
        base_result = await super().run(db, ctx, task)
        if base_result.status != "ok":
            return base_result

        parsed = _extract_brand_kit(base_result.summary)
        if parsed is None:
            # Surface as error so the CEO can ask for a retry with clearer constraints.
            return SpecialistResult(
                specialist=self.name,
                status="error",
                summary=(
                    "Creative Director produced output but it didn't contain a parseable "
                    "JSON brand kit. Ask me again with clearer constraints."
                ),
                metadata={"raw_output": base_result.summary[:800]},
                cost_cents=base_result.cost_cents,
            )

        # Short human-readable summary for the CEO to relay; full kit in metadata.
        name = parsed.get("name", "(no name)")
        tagline = parsed.get("tagline", "")
        palette_preview = ", ".join(f"{k}: {v}" for k, v in (parsed.get("palette") or {}).items())[
            :200
        ]
        summary_line = (
            f"Brand kit ready for '{name}'. Tagline: \"{tagline}\". Palette: {palette_preview}."
        )
        return SpecialistResult(
            specialist=self.name,
            status="ok",
            summary=summary_line,
            metadata={
                **base_result.metadata,
                "brand_kit": parsed,
            },
            cost_cents=base_result.cost_cents,
        )


def _extract_brand_kit(text: str) -> dict[str, Any] | None:
    """Parse the first ```json …``` block in the model output."""
    match = _JSON_BLOCK_RE.search(text)
    if match is None:
        # Fall back: maybe the model returned bare JSON without fences.
        bare = text.strip()
        if bare.startswith("{"):
            try:
                return _ensure_dict(json.loads(bare))
            except json.JSONDecodeError:
                return None
        return None
    try:
        return _ensure_dict(json.loads(match.group("body")))
    except json.JSONDecodeError:
        return None


def _ensure_dict(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


CREATIVE_DIRECTOR = CreativeDirectorSpecialist()
register(CREATIVE_DIRECTOR)

"""Creative Director — brand kit generation + iterative refinement.

If the business already has a `brand_kit` (loaded into the BusinessContext by
`_hydrate_context`), the prompt is framed as "here's the current kit, refine
only what the user asked" rather than a blank-slate generation. The result
still parses to the same JSON shape; the runtime's caller is responsible for
persisting to `businesses.brand_kit`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from helm.agents.specialists.base import (
    BusinessContext,
    LLMSpecialist,
    SpecialistResult,
    register,
)
from helm.db.models import Business

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
        # If a kit already exists, hand it to the model as context so we
        # refine rather than regenerate — preserves naming/palette continuity
        # when the user asks for "just a tweaked voice" or similar.
        framed_task = _frame_task(task, ctx)
        base_result = await super().run(db, ctx, framed_task)
        if base_result.status != "ok":
            return base_result

        parsed = _extract_brand_kit(base_result.summary)
        if parsed is None:
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

        # Persist to businesses.brand_kit when we have a business to update.
        if ctx.business_id is not None and db is not None:
            await db.execute(
                update(Business).where(Business.id == ctx.business_id).values(brand_kit=parsed)
            )
            await db.commit()

        name = parsed.get("name", "(no name)")
        tagline = parsed.get("tagline", "")
        palette_preview = ", ".join(f"{k}: {v}" for k, v in (parsed.get("palette") or {}).items())[
            :200
        ]
        refined = bool(ctx.brand_kit)
        verb = "refined" if refined else "ready"
        summary_line = (
            f"Brand kit {verb} for '{name}'. Tagline: \"{tagline}\". Palette: {palette_preview}."
        )
        return SpecialistResult(
            specialist=self.name,
            status="ok",
            summary=summary_line,
            metadata={
                **base_result.metadata,
                "brand_kit": parsed,
                "refined": refined,
            },
            cost_cents=base_result.cost_cents,
        )


def _frame_task(task: str, ctx: BusinessContext) -> str:
    """Wrap the task with context the model needs.

    Fresh generation: task only.
    Refinement: include the current kit as JSON, instruct to preserve what
    wasn't asked to change. Including the kit at the top keeps it cache-warm
    across refinement calls on the same business.
    """
    if not ctx.brand_kit:
        return task
    header = (
        "You are refining an existing brand kit. The CURRENT KIT is below; "
        "preserve every field the user did not explicitly ask to change. "
        "Return the FULL updated kit JSON (not a diff).\n\n"
        f"CURRENT KIT:\n```json\n{json.dumps(ctx.brand_kit, indent=2)}\n```\n\n"
    )
    return header + f"USER'S REQUEST:\n{task}"


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

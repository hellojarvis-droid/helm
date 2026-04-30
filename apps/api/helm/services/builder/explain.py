"""Explain layer — founder-facing summary of what changed.

Haiku 4.5 — single paragraph, plain English.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from helm.services.builder import _llm
from helm.services.builder.prompts import EXPLAIN_SYSTEM
from helm.services.builder.verify import VerifyReport

_MODEL = "claude-haiku-4-5-20251001"


async def summarize(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    user_id: uuid.UUID,
    plain_plan: str,
    touched_paths: list[str],
    verify: VerifyReport,
) -> str:
    """Return a single founder-facing paragraph."""
    user_message = json.dumps(
        {
            "applied_plan": plain_plan,
            "touched_files": touched_paths,
            "verify": dict(verify),
        },
        indent=2,
    )
    try:
        parsed = await _llm.run_step(
            db,
            project_id=project_id,
            plan_id=plan_id,
            user_id=user_id,
            step="explain",
            model=_MODEL,
            system=EXPLAIN_SYSTEM + "\nReturn ONLY a JSON object: {\"summary\": \"...\"}",
            user_message=user_message,
            estimate_cents=1,
            max_tokens=1000,
        )
    except _llm.BuilderLLMError:
        # Fall back to a stub sentence if the explain step fails —
        # we don't want a post-apply UX blocker over copy.
        return _fallback(plain_plan, touched_paths, verify)

    if isinstance(parsed, dict):
        text = str(parsed.get("summary", "")).strip()
        if text:
            return text
    return _fallback(plain_plan, touched_paths, verify)


def _fallback(plain_plan: str, touched_paths: list[str], verify: VerifyReport) -> str:
    if not touched_paths:
        return "No files changed. If this wasn't what you wanted, refine the request and try again."
    file_str = ", ".join(p.split("/")[-1] for p in touched_paths[:5])
    base = f"{plain_plan.strip()} Touched {len(touched_paths)} file(s) — {file_str}."
    if not verify["ok"]:
        return f"{base} Heads up: {verify['errors']} issue(s) came up — click Undo if preview looks off."
    if verify["warnings"]:
        return f"{base} One or two small warnings; preview should still load."
    return f"{base} Everything looks good."

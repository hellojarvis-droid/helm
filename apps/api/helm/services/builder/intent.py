"""Intent layer — parse a founder's prompt into a structured Intent.

Haiku 4.5 — cheap, fast, good enough to classify the kind of change.
"""

from __future__ import annotations

import json
import uuid
from typing import Literal, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from helm.services.builder import _llm
from helm.services.builder.prompts import INTENT_SYSTEM

_MODEL = "claude-haiku-4-5-20251001"


class Intent(TypedDict):
    kind: Literal["create", "edit", "import", "publish", "undo", "refine"]
    summary: str
    targets: list[str]
    needs_planning: bool


async def parse(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    user_prompt: str,
    project_name: str,
) -> Intent:
    """Classify the founder's intent. Raises on cap/provider errors;
    the orchestrator catches those and surfaces as 402/502 at the route
    layer.
    """
    user_message = json.dumps(
        {"project_name": project_name, "request": user_prompt}, indent=2
    )
    parsed = await _llm.run_step(
        db,
        project_id=project_id,
        plan_id=None,
        user_id=user_id,
        step="intent",
        model=_MODEL,
        system=INTENT_SYSTEM,
        user_message=user_message,
        estimate_cents=1,
        max_tokens=1000,
    )
    if not isinstance(parsed, dict):
        raise _llm.BuilderLLMError("intent: expected JSON object")

    kind_raw = str(parsed.get("kind", "edit"))
    allowed = {"create", "edit", "import", "publish", "undo", "refine"}
    kind: Literal["create", "edit", "import", "publish", "undo", "refine"] = (
        kind_raw if kind_raw in allowed else "edit"  # type: ignore[assignment]
    )
    return {
        "kind": kind,
        "summary": str(parsed.get("summary", user_prompt))[:200],
        "targets": list(parsed.get("targets") or []),
        "needs_planning": bool(parsed.get("needs_planning", True)),
    }

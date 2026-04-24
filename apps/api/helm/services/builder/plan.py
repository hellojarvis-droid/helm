"""Plan layer — Intent + project context → Plan.

Sonnet 4.6 is the default. For projects with > _OPUS_FILE_THRESHOLD
files OR an architecturally-significant prompt (keyword match), upgrade
to Opus 4.7 for better long-horizon reasoning.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from helm.services.builder import _llm
from helm.services.builder.intent import Intent
from helm.services.builder.prompts import PLAN_SYSTEM

_DEFAULT_MODEL = "claude-sonnet-4-6"
_OPUS_MODEL = "claude-opus-4-7"
_OPUS_FILE_THRESHOLD = 20
_OPUS_KEYWORDS = re.compile(
    r"\b(refactor|architecture|rewrite|migrate|authentication|auth flow|"
    r"permissions|multi-tenant|database schema|api design|payments integration)\b",
    re.IGNORECASE,
)


class Plan(TypedDict):
    plain_plan: str
    technical_plan: str
    affected_areas: list[dict[str, Any]]
    risks: str
    recommendation: str
    file_hints: list[str]
    model_used: str


def _pick_model(*, file_count: int, user_prompt: str) -> str:
    if file_count > _OPUS_FILE_THRESHOLD:
        return _OPUS_MODEL
    if _OPUS_KEYWORDS.search(user_prompt):
        return _OPUS_MODEL
    return _DEFAULT_MODEL


async def generate(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    intent: Intent,
    project_name: str,
    user_prompt: str,
    file_tree: list[str],
) -> Plan:
    """Generate a plan. `file_tree` is just paths — we don't send file
    contents into the planner for cost reasons; the executor gets
    full contents later.
    """
    model = _pick_model(file_count=len(file_tree), user_prompt=user_prompt)
    user_message = json.dumps(
        {
            "project_name": project_name,
            "founder_request": user_prompt,
            "intent": dict(intent),
            "file_tree": sorted(file_tree)[:200],
            "file_count": len(file_tree),
            "model_slug": model,
        },
        indent=2,
    )
    # 8c estimate covers a medium-sized plan on Sonnet with headroom;
    # Opus runs higher but typical output is bounded.
    estimate = 8 if model == _DEFAULT_MODEL else 40
    parsed = await _llm.run_step(
        db,
        project_id=project_id,
        plan_id=None,
        user_id=user_id,
        step="plan",
        model=model,
        system=PLAN_SYSTEM,
        user_message=user_message,
        estimate_cents=estimate,
        max_tokens=2200,
    )
    if not isinstance(parsed, dict):
        raise _llm.BuilderLLMError("plan: expected JSON object")
    return {
        "plain_plan": str(parsed.get("plain_plan", "")).strip()[:2000],
        "technical_plan": str(parsed.get("technical_plan", "")).strip()[:4000],
        "affected_areas": [
            {
                "label": str(a.get("label", ""))[:120],
                "rationale": str(a.get("rationale", ""))[:300],
            }
            for a in (parsed.get("affected_areas") or [])
            if isinstance(a, dict)
        ],
        "risks": str(parsed.get("risks", "None"))[:500],
        "recommendation": str(parsed.get("recommendation", ""))[:500],
        "file_hints": [str(p) for p in (parsed.get("file_hints") or []) if p][:40],
        "model_used": model,
    }

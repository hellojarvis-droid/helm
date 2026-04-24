"""Shared LLM helper for Builder layers.

Each layer (intent, plan, execute, explain) calls `run_step` which
handles the Anthropic request, credit reserve/commit, per-project daily
spend cap enforcement, and observability row writes. Keeping this in
one place means none of the layer modules know about credits or run
bookkeeping — they're pure prompt → JSON extractors.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import anthropic
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from helm.config import get_settings
from helm.db.models import BuilderProject, BuilderRun
from helm.services import credits
from helm.services.integration_vault import ProviderKeyMissingError

log = structlog.get_logger("helm.builder.llm")


class BuilderLLMError(Exception):
    """Layer couldn't produce parseable output or the API failed."""


# Token prices in cents per 1M tokens, aligned with other Helm services.
_PRICES_CENTS: dict[str, tuple[int, int]] = {
    "claude-sonnet-4-6": (300, 1500),
    "claude-opus-4-7": (1500, 7500),
    "claude-haiku-4-5-20251001": (25, 125),
}


def cost_cents(model: str, in_toks: int, out_toks: int) -> int:
    in_per_m, out_per_m = _PRICES_CENTS.get(model, (300, 1500))
    raw = (in_toks * in_per_m + out_toks * out_per_m) / 1_000_000
    return max(1, int(raw * 1.01 + 0.999))


async def run_step(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    plan_id: uuid.UUID | None,
    user_id: uuid.UUID,
    step: str,
    model: str,
    system: str,
    user_message: str,
    estimate_cents: int,
    max_tokens: int = 2000,
) -> Any:
    """Run one LLM step end-to-end.

    Reserves credits → calls Anthropic → parses a JSON object out of
    the response → commits actual cost. Writes a BuilderRun row for
    observability. Enforces the project's daily spend cap *before*
    reserving.
    """
    project = await db.get(BuilderProject, project_id)
    if project is None:
        raise BuilderLLMError("project not found")

    # Daily spend cap: reject before reserving.
    if project.daily_spend_cents >= project.daily_spend_cap_cents:
        raise BuilderLLMError(
            f"daily spend cap hit ({project.daily_spend_cap_cents}c)"
        )

    run = BuilderRun(
        project_id=project_id,
        plan_id=plan_id,
        step=step,
        model=model,
        status="running",
    )
    db.add(run)
    await db.flush()

    reservation_id, _ = await credits.reserve(
        db,
        user_id=user_id,
        estimate_cents=estimate_cents,
        reference_type=f"builder_{step}",
        description=f"Builder {step} on {project.name}",
        meta={"project_id": str(project_id), "plan_id": str(plan_id) if plan_id else None},
    )
    await db.commit()

    settings = get_settings()
    if not settings.anthropic_api_key:
        await credits.refund(
            db,
            user_id=user_id,
            reservation_id=reservation_id,
            reason="anthropic not configured",
        )
        run.status = "failed"
        run.error = "anthropic not configured"
        await db.commit()
        raise ProviderKeyMissingError("anthropic")

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        msg = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as e:
        await credits.refund(
            db,
            user_id=user_id,
            reservation_id=reservation_id,
            reason=f"anthropic error: {str(e)[:120]}",
        )
        run.status = "failed"
        run.error = str(e)[:300]
        await db.commit()
        raise BuilderLLMError(f"anthropic error ({step}): {e}") from e

    in_toks = msg.usage.input_tokens
    out_toks = msg.usage.output_tokens
    actual = cost_cents(model, in_toks, out_toks)
    await credits.commit(
        db,
        user_id=user_id,
        reservation_id=reservation_id,
        actual_cents=actual,
        description=f"Builder {step} · {project.name}",
        meta={"project_id": str(project_id)},
    )

    # Also bump the project's per-day spend so the cap enforces.
    project.daily_spend_cents = int(project.daily_spend_cents or 0) + actual
    await db.commit()

    text = "".join(
        getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text"
    )
    parsed = _extract_json(text)
    if parsed is None:
        run.status = "failed"
        run.error = f"unparseable output (first 200 chars): {text[:200]}"
        await db.commit()
        raise BuilderLLMError(
            f"{step}: model returned unparseable JSON: {text[:200]}"
        )

    run.status = "completed"
    run.input_tokens = in_toks
    run.output_tokens = out_toks
    run.cost_cents = actual
    # BuilderRun.output is typed as dict; wrap list outputs.
    run.output = parsed if isinstance(parsed, dict) else {"items": parsed}
    await db.commit()
    return parsed


def _extract_json(text: str) -> dict[str, Any] | list[Any] | None:
    """Pull the first JSON object or array out of a model response."""
    try:
        obj = json.loads(text)
        if isinstance(obj, (dict, list)):
            return obj
    except Exception:
        pass
    # Walk for balanced {...} or [...].
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start < 0:
            continue
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start : i + 1])
                        if isinstance(obj, (dict, list)):
                            return obj
                    except Exception:
                        break
    return None

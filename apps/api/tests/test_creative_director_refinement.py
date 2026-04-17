"""Creative Director: fresh-kit vs. refinement-of-existing-kit framing."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest
from anthropic.types import TextBlock, Usage
from helm.agents.specialists.base import BusinessContext
from helm.agents.specialists.creative_director import CreativeDirectorSpecialist, _frame_task
from helm.services import kill_switch


def _prime_kill_switch_cache(user_id) -> None:
    kill_switch._cache[user_id] = kill_switch._CacheEntry(active=False, fetched_at=time.monotonic())


@dataclass
class _Msg:
    content: list[Any]
    stop_reason: str
    usage: Usage
    model: str = "claude-sonnet-4-6"


def _stub_returning_kit(kit: dict) -> Any:
    text = f"```json\n{json.dumps(kit)}\n```"
    msg = _Msg(
        content=[TextBlock(type="text", text=text, citations=None)],
        stop_reason="end_turn",
        usage=Usage.model_construct(input_tokens=100, output_tokens=200),
    )
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = AsyncMock(return_value=msg)
    return client


def test_frame_task_without_existing_kit_returns_task_unchanged() -> None:
    ctx = BusinessContext(
        user_id=__import__("uuid").UUID(int=1),
        business_id=None,
        session_id=__import__("uuid").UUID(int=2),
    )
    assert _frame_task("brand my candle biz", ctx) == "brand my candle biz"


def test_frame_task_with_existing_kit_prepends_refinement_header() -> None:
    ctx = BusinessContext(
        user_id=__import__("uuid").UUID(int=1),
        business_id=None,
        session_id=__import__("uuid").UUID(int=2),
        brand_kit={"name": "Ember", "tagline": "slow fires"},
    )
    framed = _frame_task("make the voice more playful", ctx)
    assert "CURRENT KIT" in framed
    assert "Ember" in framed
    assert "USER'S REQUEST" in framed
    assert framed.endswith("make the voice more playful")


@pytest.mark.asyncio
async def test_refinement_flag_set_when_kit_present() -> None:
    spec = CreativeDirectorSpecialist()
    new_kit = {
        "name": "Ember",
        "tagline": "refined",
        "palette": {"primary": "#111111"},
        "typography": {"display": "Inter", "body": "Inter"},
        "voice": {"description": "playful", "sample_sentences": ["a", "b", "c"]},
        "logo_concept": "refined logo",
        "moodboard_keywords": ["x"],
    }
    spec._client = _stub_returning_kit(new_kit)  # type: ignore[assignment]

    ctx_with_kit = BusinessContext(
        user_id=__import__("uuid").UUID(int=1),
        business_id=None,  # None so we skip the DB update path
        session_id=__import__("uuid").UUID(int=2),
        brand_kit={"name": "Ember", "tagline": "original"},
    )
    _prime_kill_switch_cache(ctx_with_kit.user_id)
    result = await spec.run(db=None, ctx=ctx_with_kit, task="make it playful")  # type: ignore[arg-type]

    assert result.status == "ok"
    assert result.metadata["refined"] is True
    assert "refined for" in result.summary.lower()


@pytest.mark.asyncio
async def test_fresh_generation_when_no_kit() -> None:
    spec = CreativeDirectorSpecialist()
    new_kit = {
        "name": "Sparrow",
        "tagline": "first",
        "palette": {"primary": "#222222"},
        "typography": {"display": "Lora", "body": "Inter"},
        "voice": {"description": "warm", "sample_sentences": ["a", "b", "c"]},
        "logo_concept": "sparrow mark",
        "moodboard_keywords": ["x"],
    }
    spec._client = _stub_returning_kit(new_kit)  # type: ignore[assignment]

    ctx_no_kit = BusinessContext(
        user_id=__import__("uuid").UUID(int=1),
        business_id=None,
        session_id=__import__("uuid").UUID(int=2),
        brand_kit={},
    )
    _prime_kill_switch_cache(ctx_no_kit.user_id)
    result = await spec.run(db=None, ctx=ctx_no_kit, task="brand my bird app")  # type: ignore[arg-type]

    assert result.status == "ok"
    assert result.metadata["refined"] is False
    assert "ready for" in result.summary.lower()

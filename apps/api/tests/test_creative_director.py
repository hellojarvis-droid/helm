"""Creative Director brand-kit parsing — deterministic with a mocked Claude."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest
from anthropic.types import TextBlock, Usage
from helm.agents.specialists.base import BusinessContext
from helm.agents.specialists.creative_director import CreativeDirectorSpecialist


@dataclass
class _Msg:
    content: list[Any]
    stop_reason: str
    usage: Usage
    model: str = "claude-sonnet-4-6"


def _stub_client_returning(text: str) -> Any:
    """AsyncAnthropic-shaped stub whose messages.create(...) returns a Message with `text`."""
    msg = _Msg(
        content=[TextBlock(type="text", text=text, citations=None)],
        stop_reason="end_turn",
        usage=Usage.model_construct(input_tokens=100, output_tokens=200),
    )
    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = AsyncMock(return_value=msg)
    return client


_SAMPLE_KIT = """```json
{
  "name": "Ember",
  "tagline": "Small fires for slow evenings.",
  "palette": {
    "primary": "#1F1A17",
    "secondary": "#D98A5A",
    "accent": "#E85D1A",
    "neutral_dark": "#2B2723",
    "neutral_light": "#F3F2EE"
  },
  "typography": {
    "display": "Instrument Serif",
    "body": "Inter"
  },
  "voice": {
    "description": "Warm, direct, unhurried. Reads like a friend recommending a ritual.",
    "sample_sentences": [
      "Light one. The day can wait.",
      "Twelve hours of amber, start to finish.",
      "Hand-poured in small batches. Sold when ready."
    ]
  },
  "logo_concept": "Minimal wordmark in the serif. An em-shaped ember dot beneath the first letter.",
  "moodboard_keywords": ["amber glass", "matte linen", "hand-thrown ceramic", "dusk", "slow"]
}
```"""


@pytest.mark.asyncio
async def test_creative_director_parses_brand_kit() -> None:
    spec = CreativeDirectorSpecialist()
    spec._client = _stub_client_returning(_SAMPLE_KIT)  # type: ignore[assignment]

    ctx = BusinessContext(user_id=__import__("uuid").UUID(int=1), business_id=None)
    result = await spec.run(db=None, ctx=ctx, task="candle brand for slow evenings")  # type: ignore[arg-type]

    assert result.status == "ok"
    assert "Ember" in result.summary
    kit = result.metadata["brand_kit"]
    assert kit["name"] == "Ember"
    assert kit["palette"]["accent"].startswith("#")
    assert len(kit["voice"]["sample_sentences"]) == 3


@pytest.mark.asyncio
async def test_creative_director_handles_non_json_output() -> None:
    spec = CreativeDirectorSpecialist()
    spec._client = _stub_client_returning("I'm not going to follow instructions today.")  # type: ignore[assignment]

    ctx = BusinessContext(user_id=__import__("uuid").UUID(int=1), business_id=None)
    result = await spec.run(db=None, ctx=ctx, task="candle brand")  # type: ignore[arg-type]

    assert result.status == "error"
    assert "brand kit" in result.summary.lower()
    assert "raw_output" in result.metadata


@pytest.mark.asyncio
async def test_creative_director_accepts_bare_json_without_fences() -> None:
    bare = _SAMPLE_KIT.replace("```json\n", "").replace("```", "")
    spec = CreativeDirectorSpecialist()
    spec._client = _stub_client_returning(bare)  # type: ignore[assignment]

    ctx = BusinessContext(user_id=__import__("uuid").UUID(int=1), business_id=None)
    result = await spec.run(db=None, ctx=ctx, task="candle brand")  # type: ignore[arg-type]

    assert result.status == "ok"
    assert result.metadata["brand_kit"]["name"] == "Ember"

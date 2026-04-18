"""Growth Analyst — weekly strategic review.

Per AGENTS.md §9 and BUILD_PLAN.md Phase 5.6. Reads the BusinessContext
it was given (recent_events, brand_kit) and produces a one-page review
with Wins / Watch / Recommendations (exactly 3, ranked). No Composio
toolkits — this specialist operates on the data already hydrated into
its context plus optional `web_search` for market benchmarks.
"""

from __future__ import annotations

from pathlib import Path

from anthropic.types import ToolUnionParam

from helm.agents.specialists.base import LLMSpecialist, register

_PROMPT_PATH = Path(__file__).parent / "prompts" / "growth_analyst.md"

_WEB_SEARCH_TOOL: ToolUnionParam = {
    "name": "web_search",
    "type": "web_search_20250305",
    "max_uses": 4,
}


def build() -> LLMSpecialist:
    return LLMSpecialist(
        name="growth_analyst",
        # Opus for strategic synthesis — the output gates weekly decisions.
        model="claude-opus-4-7",
        system_prompt=_PROMPT_PATH.read_text(),
        tools=[_WEB_SEARCH_TOOL],
        composio_toolkits=[],
        max_tokens=3500,
    )


GROWTH_ANALYST = build()
register(GROWTH_ANALYST)

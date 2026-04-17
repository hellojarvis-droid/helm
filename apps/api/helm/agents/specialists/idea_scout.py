"""Idea Scout — the first real specialist.

Uses Anthropic's server-executed web_search tool to find proven business
concepts. Single-shot call: the CEO hands Idea Scout the user's constraints,
Idea Scout returns 3 ideas with sourced evidence.

System prompt lives in `prompts/idea_scout.md` (gitignored from prettier).
"""

from __future__ import annotations

from pathlib import Path

from anthropic.types import ToolUnionParam

from helm.agents.specialists.base import LLMSpecialist, register

_PROMPT_PATH = Path(__file__).parent / "prompts" / "idea_scout.md"

_WEB_SEARCH_TOOL: ToolUnionParam = {
    "name": "web_search",
    "type": "web_search_20250305",
    "max_uses": 8,
}


def build() -> LLMSpecialist:
    return LLMSpecialist(
        name="idea_scout",
        model="claude-opus-4-7",
        system_prompt=_PROMPT_PATH.read_text(),
        tools=[_WEB_SEARCH_TOOL],
        # Optional Composio toolkits — used only when the business has them
        # connected. When none connected, falls back to web_search only.
        composio_toolkits=["reddit", "hackernews", "product_hunt"],
        max_tokens=6000,
    )


IDEA_SCOUT = build()
register(IDEA_SCOUT)

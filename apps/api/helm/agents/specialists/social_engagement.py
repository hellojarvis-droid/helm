"""Social Engagement — polls organic social, replies on-brand, escalates.

Per AGENTS.md §5 and BUILD_PLAN.md Phase 5.3. Reads from the business's
connected social Composio toolkits (Instagram, TikTok, X, LinkedIn,
Threads). Rate-limited to 20 replies per delegation call via the system
prompt — the CEO typically re-invokes every ~2 minutes during active
hours.
"""

from __future__ import annotations

from pathlib import Path

from anthropic.types import ToolUnionParam

from helm.agents.specialists.base import LLMSpecialist, register

_PROMPT_PATH = Path(__file__).parent / "prompts" / "social_engagement.md"

_WEB_SEARCH_TOOL: ToolUnionParam = {
    "name": "web_search",
    "type": "web_search_20250305",
    "max_uses": 3,
}


def build() -> LLMSpecialist:
    return LLMSpecialist(
        name="social_engagement",
        # Sonnet — stays responsive at polling cadence without Opus cost.
        model="claude-sonnet-4-6",
        system_prompt=_PROMPT_PATH.read_text(),
        tools=[_WEB_SEARCH_TOOL],
        composio_toolkits=[
            "instagram",
            "tiktok",
            "twitter",
            "x_dot_com",
            "linkedin",
            "threads",
        ],
        max_tokens=4500,
    )


SOCIAL_ENGAGEMENT = build()
register(SOCIAL_ENGAGEMENT)

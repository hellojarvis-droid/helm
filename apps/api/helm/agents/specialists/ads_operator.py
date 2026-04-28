"""Ads Operator — paid acquisition across Meta, Google, TikTok.

Per AGENTS.md §4 and BUILD_PLAN.md Phase 5.1. Invoked by the CEO to
launch/tune/pause campaigns. Does not spend money without an approval
trail the CEO already staged — the system prompt enforces this by refusing
to execute a spending action when no matching approval lands in
`ctx.recent_events`.
"""

from __future__ import annotations

from pathlib import Path

from anthropic.types import ToolUnionParam

from helm.agents.specialists.base import LLMSpecialist, register

_PROMPT_PATH = Path(__file__).parent / "prompts" / "ads_operator.md"

_WEB_SEARCH_TOOL: ToolUnionParam = {
    "name": "web_search",
    "type": "web_search_20250305",
    "max_uses": 3,
}


def build() -> LLMSpecialist:
    return LLMSpecialist(
        name="ads_operator",
        model="claude-sonnet-4-6",
        system_prompt=_PROMPT_PATH.read_text(),
        tools=[_WEB_SEARCH_TOOL],
        composio_toolkits=["meta_ads", "google_ads", "tiktok_ads"],
        max_tokens=6000,
        # TikTok small-budget self-serve has no public API; escalate to the
        # desktop sandbox when Composio's tiktok_ads coverage falls short.
        can_escalate_to_computer_use=True,
    )


ADS_OPERATOR = build()
register(ADS_OPERATOR)

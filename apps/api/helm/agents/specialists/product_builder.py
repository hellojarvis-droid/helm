"""Product Builder — turns a concept into a live Shopify store.

Real specialist (replaces the stub). Uses the LLMSpecialist tool-use loop with
Composio toolkits for Shopify, Printful/CJ, and Namecheap. The CEO Agent
delegates here after Creative Director has produced a brand kit; this
specialist assumes `ctx.brand_kit` is already populated.

Per AGENTS.md §3 and BUILD_PLAN.md Phase 3.2: from concept → live store in
under 15 minutes end-to-end. The system prompt lives next to this file.
"""

from __future__ import annotations

from pathlib import Path

from anthropic.types import ToolUnionParam

from helm.agents.specialists.base import LLMSpecialist, register

_PROMPT_PATH = Path(__file__).parent / "prompts" / "product_builder.md"

_WEB_SEARCH_TOOL: ToolUnionParam = {
    "name": "web_search",
    "type": "web_search_20250305",
    "max_uses": 5,
}


def build() -> LLMSpecialist:
    return LLMSpecialist(
        name="product_builder",
        # Sonnet is enough — Product Builder executes deterministic steps, not
        # strategy. Reserves Opus budget for the CEO.
        model="claude-sonnet-4-6",
        system_prompt=_PROMPT_PATH.read_text(),
        tools=[_WEB_SEARCH_TOOL],
        # Loaded at run-time only when the business has them connected.
        composio_toolkits=["shopify", "printful", "namecheap", "cj_dropshipping"],
        # Store build is a longer conversation than ideation — up the budget.
        max_tokens=8000,
        # Some supplier portals are web-only; escalate when Composio doesn't
        # cover the supplier the user picked.
        can_escalate_to_computer_use=True,
    )


PRODUCT_BUILDER = build()
register(PRODUCT_BUILDER)

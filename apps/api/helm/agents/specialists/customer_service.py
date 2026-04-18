"""Customer Service — resolves post-purchase tickets.

Per AGENTS.md §6 and BUILD_PLAN.md Phase 5.4. Composio toolkits: gorgias,
intercom, shopify (order lookups), gmail. Autonomous envelope: refunds up
to $50, standard policy answers, order status, address changes before
fulfillment. Anything larger routes through `request_user_approval` via
the CEO.
"""

from __future__ import annotations

from pathlib import Path

from anthropic.types import ToolUnionParam

from helm.agents.specialists.base import LLMSpecialist, register

_PROMPT_PATH = Path(__file__).parent / "prompts" / "customer_service.md"

_WEB_SEARCH_TOOL: ToolUnionParam = {
    "name": "web_search",
    "type": "web_search_20250305",
    "max_uses": 2,
}


def build() -> LLMSpecialist:
    return LLMSpecialist(
        name="customer_service",
        model="claude-sonnet-4-6",
        system_prompt=_PROMPT_PATH.read_text(),
        tools=[_WEB_SEARCH_TOOL],
        composio_toolkits=["gorgias", "intercom", "shopify", "gmail"],
        max_tokens=5000,
    )


CUSTOMER_SERVICE = build()
register(CUSTOMER_SERVICE)

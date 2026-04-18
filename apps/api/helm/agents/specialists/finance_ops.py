"""Finance & Ops — reconciliation, cash reporting, anomaly detection.

Per AGENTS.md §7 and BUILD_PLAN.md Phase 5.5. The last of the eight
specialists to go real. Reads Stripe + Shopify + QuickBooks/Xero via
Composio AND the business's own event log (spend_authorized,
spend_declined, revenue_received) from ctx.recent_events.

Cadences the CEO uses to invoke:
  - Daily: reconciliation
  - Weekly: cash report
  - Monthly: P&L
  - On-demand: "how's cashflow?" / anomaly escalations
"""

from __future__ import annotations

from pathlib import Path

from anthropic.types import ToolUnionParam

from helm.agents.specialists.base import LLMSpecialist, register

_PROMPT_PATH = Path(__file__).parent / "prompts" / "finance_ops.md"

_WEB_SEARCH_TOOL: ToolUnionParam = {
    "name": "web_search",
    "type": "web_search_20250305",
    "max_uses": 2,
}


def build() -> LLMSpecialist:
    return LLMSpecialist(
        name="finance_ops",
        # Sonnet — precision over creativity. Reconciliation is deterministic.
        model="claude-sonnet-4-6",
        system_prompt=_PROMPT_PATH.read_text(),
        tools=[_WEB_SEARCH_TOOL],
        composio_toolkits=["stripe", "shopify", "quickbooks", "xero"],
        # P&L generation can be long — higher budget than the chat specialists.
        max_tokens=7000,
    )


FINANCE_OPS = build()
register(FINANCE_OPS)

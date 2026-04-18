"""Stub specialists — characters in place, capability arrives later.

These preserve each specialist's voice (per AGENTS.md sections 3-9) so the CEO
Agent can coherently tell the user what it *would* do. No LLM calls —
instant, zero-cost returns.

Real implementations land in the order of user-visible impact:
  Session 3: Product Builder + Creative Director (so the first launch works)
  Session 4: Ads Operator + Growth Analyst (so the launch has revenue)
  Session 5: Social Engagement + Customer Service (so retention works)
  Session 6: Finance & Ops (month-end, reporting)
"""

from __future__ import annotations

from helm.agents.specialists.base import StubSpecialist, register

_STUBS = [
    # Real specialists (not stubs):
    #   product_builder   — specialists/product_builder.py
    #   creative_director — specialists/creative_director.py
    #   idea_scout        — specialists/idea_scout.py
    #   ads_operator      — specialists/ads_operator.py
    #   growth_analyst    — specialists/growth_analyst.py
    StubSpecialist(
        name="social_engagement",
        persona_note="Social Engagement",
        what_i_would_do=(
            "poll the business's Instagram / TikTok / X / LinkedIn / Threads "
            "every 2 minutes, reply to pre- and post-purchase questions on-brand, "
            "and flag anything that needs CS, legal, or press escalation"
        ),
        online_in="Session 5",
    ),
    StubSpecialist(
        name="customer_service",
        persona_note="Customer Service",
        what_i_would_do=(
            "resolve Shopify order questions and Gorgias tickets within policy, "
            "refund up to $50 without approval, and escalate anything involving "
            "legal, injury, or unhappy VIPs"
        ),
        online_in="Session 5",
    ),
    StubSpecialist(
        name="finance_ops",
        persona_note="Finance & Ops",
        what_i_would_do=(
            "reconcile Stripe charges against Shopify orders daily, push a "
            "monthly P&L into QuickBooks, and page you on card anomalies or "
            "near-cap spend"
        ),
        online_in="Session 6",
    ),
]


for stub in _STUBS:
    register(stub)

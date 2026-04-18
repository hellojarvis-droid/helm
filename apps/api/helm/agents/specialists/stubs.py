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
    #   social_engagement — specialists/social_engagement.py
    #   customer_service  — specialists/customer_service.py
    StubSpecialist(
        name="finance_ops",
        persona_note="Finance & Ops",
        what_i_would_do=(
            "reconcile Stripe charges against Shopify orders daily, push a "
            "monthly P&L into QuickBooks, and page you on card anomalies or "
            "near-cap spend"
        ),
        online_in="Session 29",
    ),
]


for stub in _STUBS:
    register(stub)

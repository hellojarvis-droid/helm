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
    StubSpecialist(
        name="product_builder",
        persona_note="Product Builder",
        what_i_would_do=(
            "pick a domain, spin up a Shopify store on the Dawn theme, load "
            "5-10 SKUs from Printful or CJ Dropshipping, install standard "
            "policies, connect Stripe via the business's Stripe Issuing card, "
            "run a Lighthouse check, and hand you a live URL inside 15 minutes"
        ),
        online_in="Session 3",
    ),
    StubSpecialist(
        name="creative_director",
        persona_note="Creative Director",
        what_i_would_do=(
            "generate a brand kit (logo, palette, type pairing, voice), write "
            "product copy that's benefit-led, and produce 3-5 static + video "
            "ad variants with captions burned in"
        ),
        online_in="Session 3",
    ),
    StubSpecialist(
        name="ads_operator",
        persona_note="Ads Operator",
        what_i_would_do=(
            "launch Advantage+ / PMax / Smart+ campaigns at the approved "
            "daily budget, set auto-kill rules at ROAS < 1.5 after 48h, and "
            "pace spend across Meta / Google / TikTok by marginal ROAS"
        ),
        online_in="Session 4",
    ),
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
    StubSpecialist(
        name="growth_analyst",
        persona_note="Growth Analyst",
        what_i_would_do=(
            "run a weekly strategic review with ROAS / CAC / LTV / conversion, "
            "flag anomalies > 25% WoW, and return three recommendations with "
            "confidence and reversibility ratings"
        ),
        online_in="Session 4",
    ),
]


for stub in _STUBS:
    register(stub)

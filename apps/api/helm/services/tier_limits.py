"""Tier-based limits for Helm subscriptions.

Per docs/PRD.md §7 pricing tiers. These are the hard ceilings we enforce
synchronously at write-time (business creation, etc). Overage billing on
tokens lands in a later session via Stripe metered pricing; for now,
token caps are reported but not blocking.

Tiers are stored as a string on users.tier. Unknown tiers fall back to
the most restrictive ("founder") so a mistyped row never accidentally
unlocks more capability than the user is paying for.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TierLimits:
    tier: str
    max_businesses: int  # 0 = unlimited
    monthly_tokens: int  # 0 = unlimited
    display_name: str


# CLAUDE.md §2 lists founder / operator / portfolio as the tier enum. Numbers
# from PRD.md §7. `max_businesses=0` and `monthly_tokens=0` both mean "no cap".
_TIERS: dict[str, TierLimits] = {
    "founder": TierLimits(
        tier="founder",
        max_businesses=3,
        monthly_tokens=2_000_000,
        display_name="Founder",
    ),
    "operator": TierLimits(
        tier="operator",
        max_businesses=10,
        monthly_tokens=10_000_000,
        display_name="Operator",
    ),
    "portfolio": TierLimits(
        tier="portfolio",
        max_businesses=0,
        monthly_tokens=0,
        display_name="Portfolio",
    ),
}


def get_limits(tier: str) -> TierLimits:
    """Return the limits for `tier`. Unknown tiers fall back to 'founder' — the
    most restrictive — so a bad value never accidentally unlocks capability."""
    return _TIERS.get(tier, _TIERS["founder"])


class TierLimitExceeded(Exception):  # noqa: N818 — reads naturally in raise sites
    """Raised when an action would push the user over a hard tier cap."""

    def __init__(self, tier: str, limit_name: str, current: int, allowed: int) -> None:
        self.tier = tier
        self.limit_name = limit_name
        self.current = current
        self.allowed = allowed
        super().__init__(
            f"tier '{tier}' {limit_name} limit reached: {current}/{allowed}. Upgrade to unblock."
        )

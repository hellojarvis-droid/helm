"""Stripe Billing — customer + subscription lifecycle for Helm tiers.

Separate from `stripe_client` (which handles Connect + Issuing for the
user's businesses) because this is about billing the USER for their
Helm subscription — different account, different lifecycle.

Flow:
  1. Client calls POST /billing/checkout → we ensure a Stripe customer
     for this user, create a Checkout Session for the chosen price, and
     return the session URL.
  2. User completes Checkout on Stripe's hosted page.
  3. Stripe fires customer.subscription.created → our webhook updates
     users.stripe_subscription_id + status + price_id + tier.
  4. subscription.updated keeps status/tier in sync; deleted flips tier
     back to the default and status to canceled.
"""

from __future__ import annotations

from typing import Any

import stripe

from helm.config import get_settings
from helm.services.stripe_client import _configured_stripe, _in_thread


def _price_to_tier() -> dict[str, str]:
    """Build the price→tier lookup from current settings."""
    settings = get_settings()
    out: dict[str, str] = {}
    if settings.stripe_price_founder:
        out[settings.stripe_price_founder] = "founder"
    if settings.stripe_price_operator:
        out[settings.stripe_price_operator] = "operator"
    if settings.stripe_price_portfolio:
        out[settings.stripe_price_portfolio] = "portfolio"
    return out


def tier_for_price(price_id: str | None) -> str | None:
    """Return the Helm tier that corresponds to the given Stripe price, or
    None if no mapping is configured (unknown price)."""
    if not price_id:
        return None
    return _price_to_tier().get(price_id)


async def get_or_create_customer(user_id: str, email: str, existing: str | None) -> str:
    """Return the user's Stripe Customer ID, creating one if absent."""
    if existing:
        return existing
    s = _configured_stripe()

    def _create() -> str:
        customer = s.Customer.create(
            email=email,
            metadata={"helm_user_id": user_id},
        )
        return str(customer.id)

    return await _in_thread(_create)


async def create_checkout_session(
    *,
    customer_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Start a Stripe Checkout Session for a subscription. Returns the URL."""
    s = _configured_stripe()

    def _create() -> str:
        session = s.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            allow_promotion_codes=True,
        )
        if not session.url:
            raise RuntimeError("Stripe returned a session without a URL")
        return str(session.url)

    return await _in_thread(_create)


def extract_price_id(subscription: dict[str, Any]) -> str | None:
    """Pull the first item's price ID out of a subscription object."""
    items = subscription.get("items") or {}
    data = items.get("data") if isinstance(items, dict) else None
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    price = first.get("price") if isinstance(first, dict) else None
    if isinstance(price, dict):
        pid = price.get("id")
        return str(pid) if pid else None
    return None


def extract_customer_id(subscription: dict[str, Any]) -> str | None:
    val = subscription.get("customer")
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        cid = val.get("id")
        return str(cid) if cid else None
    return None


# Re-exported for tests that want the raw SDK error type without importing stripe.
StripeSignatureError = stripe.SignatureVerificationError

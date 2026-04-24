"""Stripe SDK wrappers — Connect + Issuing.

Phase 2's money spine. All calls sit behind three guardrails:

  1. Test-mode by default. Production flip happens only when the user
     explicitly provides a live `sk_live_...` key AND STRIPE_ISSUING_ENABLED
     is set true for Issuing writes. Per CLAUDE.md §3 rule: no live money
     without explicit user action.
  2. The blocking Stripe SDK is wrapped in `_in_thread` so we don't starve
     the async event loop during webhook bursts.
  3. Signature verification uses `stripe.Webhook.construct_event` (constant-
     time). Anything posting to /webhooks/stripe without a valid sig gets 401.

Session 7 ships Connect onboarding + webhook routing. Issuing cardholder +
card creation land in Session 8 once the Issuing-for-Agents application
clears; the shape of the functions here is set up so the bodies drop in
cleanly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import stripe

from helm.config import get_settings


@dataclass(frozen=True, slots=True)
class OnboardingLink:
    account_id: str
    onboarding_url: str
    expires_at: int  # unix timestamp


def _configured_stripe() -> Any:
    """Return the stripe module with the platform API key set.

    We intentionally mutate the module-level `stripe.api_key` rather than
    construct a client instance — the stripe SDK's blocking API uses the
    module-level key and there's no benefit to per-call client setup at
    our scale. Calling this before every op makes reconfiguration in tests
    (monkey-patching settings) just work.
    """
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured")
    stripe.api_key = settings.stripe_secret_key
    return stripe


# ────────────────────────────────────────────────────────────────────
# Connect
# ────────────────────────────────────────────────────────────────────


async def create_connect_account(
    business_name: str,
    business_email: str,
    country: str = "US",
) -> str:
    """Create a Stripe Connect Custom account for a business.

    Custom accounts let us control the full flow (onboarding link, UI) rather
    than redirecting users to Stripe-hosted Express onboarding. Returns the
    Stripe `acct_...` ID.
    """
    s = _configured_stripe()

    def _create() -> str:
        acct = s.Account.create(
            type="custom",
            country=country,
            email=business_email,
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
            business_profile={"name": business_name},
        )
        return str(acct.id)

    return await _in_thread(_create)


async def create_account_link(
    account_id: str,
    return_url: str,
    refresh_url: str,
) -> OnboardingLink:
    """Create a one-time onboarding link for an account. Stripe returns a
    URL that expires (~15 min) — the client opens it, user completes KYC,
    Stripe redirects back to our return_url."""
    s = _configured_stripe()

    def _create() -> OnboardingLink:
        link = s.AccountLink.create(
            account=account_id,
            refresh_url=refresh_url,
            return_url=return_url,
            type="account_onboarding",
        )
        return OnboardingLink(
            account_id=account_id,
            onboarding_url=str(link.url),
            expires_at=int(link.expires_at),
        )

    return await _in_thread(_create)


async def get_account(account_id: str) -> dict[str, Any]:
    """Fetch a connected account's current state. Used by webhook handlers
    and status endpoints to decide whether onboarding has completed."""
    s = _configured_stripe()

    def _get() -> dict[str, Any]:
        acct = s.Account.retrieve(account_id)
        return dict(acct.to_dict_recursive()) if hasattr(acct, "to_dict_recursive") else dict(acct)

    return await _in_thread(_get)


def account_onboarding_complete(account: dict[str, Any]) -> bool:
    """Stripe's canonical onboarding-complete predicate: `details_submitted`
    true AND no outstanding `requirements.currently_due` items."""
    if not account.get("details_submitted"):
        return False
    reqs = account.get("requirements") or {}
    currently_due = reqs.get("currently_due") or []
    return not currently_due


# ────────────────────────────────────────────────────────────────────
# Issuing (Session 8+ — signatures only)
# ────────────────────────────────────────────────────────────────────


async def create_issuing_cardholder(
    account_id: str,
    business_name: str,
    business_email: str,
) -> str:
    """Create a Stripe Issuing cardholder for a business. Returns `ich_...`.

    Session 8 wires this. Raises until the feature flag is flipped.
    """
    settings = get_settings()
    if not settings.stripe_issuing_enabled:
        raise RuntimeError(
            "Issuing not yet enabled (STRIPE_ISSUING_ENABLED=false). "
            "Flip on after the Issuing-for-Agents application is approved."
        )
    s = _configured_stripe()

    def _create() -> str:
        ch = s.issuing.Cardholder.create(
            stripe_account=account_id,
            name=business_name,
            email=business_email,
            status="active",
            type="company",
        )
        return str(ch.id)

    return await _in_thread(_create)


async def create_issuing_card(
    account_id: str,
    cardholder_id: str,
    weekly_spend_cap_cents: int,
    allowed_mcc_codes: list[str] | None = None,
) -> str:
    """Create a virtual Issuing card with spending controls enforced at the
    authorization layer by Stripe. Returns `ic_...`.

    Session 8 wires this.
    """
    settings = get_settings()
    if not settings.stripe_issuing_enabled:
        raise RuntimeError("Issuing not yet enabled")
    s = _configured_stripe()

    def _create() -> str:
        controls: dict[str, Any] = {
            "spending_limits": [
                {"amount": weekly_spend_cap_cents, "interval": "weekly"},
            ],
        }
        if allowed_mcc_codes:
            controls["allowed_categories"] = allowed_mcc_codes
        card = s.issuing.Card.create(
            stripe_account=account_id,
            cardholder=cardholder_id,
            currency="usd",
            type="virtual",
            spending_controls=controls,
        )
        return str(card.id)

    return await _in_thread(_create)


async def update_issuing_caps(
    account_id: str,
    card_id: str,
    weekly_spend_cap_cents: int,
    per_auth_cap_cents: int,
    allowed_mcc_codes: list[str] | None = None,
) -> None:
    """Push the weekly cap, per-authorization cap, and (optional) MCC allowlist
    onto the Issuing card.

    Stripe takes a single spending_controls object — we rebuild it every time
    so the card's view stays a mirror of the business row.
    `allowed_mcc_codes` uses Stripe's category names, not MCC codes; the caller
    is responsible for already having mapped to Stripe's vocabulary if needed.
    Passing None clears the allowlist (Stripe falls back to "all categories").
    """
    settings = get_settings()
    if not settings.stripe_issuing_enabled:
        raise RuntimeError("Issuing not yet enabled")
    s = _configured_stripe()

    limits: list[dict[str, Any]] = [
        {"amount": weekly_spend_cap_cents, "interval": "weekly"},
        {"amount": per_auth_cap_cents, "interval": "per_authorization"},
    ]
    controls: dict[str, Any] = {"spending_limits": limits}
    if allowed_mcc_codes is not None:
        controls["allowed_categories"] = allowed_mcc_codes

    def _update() -> None:
        s.issuing.Card.modify(
            card_id,
            stripe_account=account_id,
            spending_controls=controls,
        )

    await _in_thread(_update)


async def approve_authorization(
    authorization_id: str,
    account_id: str,
) -> None:
    """Enforce an approved decision at Stripe's edge.

    Stripe sends `issuing_authorization.request` and waits for our decision.
    The webhook HTTP response body is advisory only — the binding decision
    happens via this server-to-server call against the Issuing API on the
    connected account.
    """
    s = _configured_stripe()

    def _approve() -> None:
        s.issuing.Authorization.approve(authorization_id, stripe_account=account_id)

    await _in_thread(_approve)


async def decline_authorization(
    authorization_id: str,
    account_id: str,
    reason: str | None = None,
) -> None:
    """Enforce a declined decision at Stripe's edge.

    Stripe accepts an optional free-form reason that surfaces in the dashboard
    for later review. We pass our decision's reason string through so the
    audit trail is complete.
    """
    s = _configured_stripe()

    def _decline() -> None:
        kwargs: dict[str, Any] = {"stripe_account": account_id}
        if reason:
            kwargs["metadata"] = {"helm_decline_reason": reason}
        s.issuing.Authorization.decline(authorization_id, **kwargs)

    await _in_thread(_decline)


# ────────────────────────────────────────────────────────────────────
# Webhooks
# ────────────────────────────────────────────────────────────────────


def verify_webhook(payload: bytes, signature_header: str) -> Any:
    """Verify + parse a Stripe webhook. Raises on invalid signature.

    We never trust the payload without this check — Stripe's own SDK helper
    does constant-time comparison and tolerance-windowed timestamp verification.
    """
    settings = get_settings()
    secret = settings.stripe_webhook_secret
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured")
    return stripe.Webhook.construct_event(payload, signature_header, secret)


async def _in_thread[T](fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Stripe SDK is blocking — run each call in asyncio's default executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


# ────────────────────────────────────────────────────────────────────
# Checkout (Helm Storefront → connected account)
# ────────────────────────────────────────────────────────────────────


async def create_credits_checkout_session(
    *,
    user_id: str,
    credit_amount_cents: int,
    fee_cents: int,
    total_charge_cents: int,
    payment_method: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """One-shot checkout for a credits top-up on Helm's platform account.

    Unlike `create_direct_checkout_session` (which bills the connected
    merchant on a storefront purchase), this runs on Helm's own Stripe
    account — we're selling credits to the user, so we are the
    merchant of record. Two line items so the user sees the breakdown
    on the hosted checkout page.
    """
    s = _configured_stripe()

    def _create() -> str:
        payment_method_types: list[str]
        if payment_method == "card":
            payment_method_types = ["card"]
        elif payment_method == "us_bank_account":
            payment_method_types = ["us_bank_account"]
        else:
            raise ValueError(f"unsupported payment_method: {payment_method}")

        line_items = [
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": credit_amount_cents,
                    "product_data": {
                        "name": f"Helm credits: ${credit_amount_cents / 100:.2f}",
                        "description": (
                            "Credits land in your Helm balance on payment success."
                        ),
                    },
                },
                "quantity": 1,
            },
        ]
        if fee_cents > 0:
            line_items.append(
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": fee_cents,
                        "product_data": {
                            "name": "Stripe processing fee",
                            "description": (
                                "Card-network fee charged by Stripe. "
                                "Not a Helm charge."
                            ),
                        },
                    },
                    "quantity": 1,
                }
            )

        session = s.checkout.Session.create(
            mode="payment",
            payment_method_types=payment_method_types,
            line_items=line_items,
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=user_id,
            metadata={
                "kind": "credits_topup",
                "user_id": user_id,
                "credit_amount_cents": str(credit_amount_cents),
                "fee_cents": str(fee_cents),
                "total_charge_cents": str(total_charge_cents),
                "payment_method": payment_method,
            },
        )
        return str(session.url)

    return await _in_thread(_create)


async def create_direct_checkout_session(
    *,
    connected_account_id: str,
    product_name: str,
    unit_amount_cents: int,
    currency: str,
    quantity: int,
    success_url: str,
    cancel_url: str,
    client_reference_id: str | None = None,
    description: str | None = None,
    image_urls: list[str] | None = None,
) -> str:
    """Create a one-shot Stripe Checkout session as a Direct Charge on the
    connected account. Returns the hosted-page URL.

    "Direct charge" means the customer pays the connected account (the
    business) directly; Stripe's platform-fee mechanics don't apply — we
    don't skim. When Helm takes a fee later, add `payment_intent_data.
    application_fee_amount` here.
    """
    s = _configured_stripe()

    def _create() -> str:
        product_data: dict[str, Any] = {"name": product_name}
        if description:
            product_data["description"] = description
        if image_urls:
            product_data["images"] = image_urls[:8]  # Stripe accepts up to 8
        session = s.checkout.Session.create(
            stripe_account=connected_account_id,
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": currency.lower(),
                        "unit_amount": unit_amount_cents,
                        "product_data": product_data,
                    },
                    "quantity": quantity,
                }
            ],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=client_reference_id,
        )
        return str(session.url)

    return await _in_thread(_create)

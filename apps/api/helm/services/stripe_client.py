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


async def update_issuing_weekly_cap(
    account_id: str,
    card_id: str,
    weekly_spend_cap_cents: int,
) -> None:
    """Push a new weekly spending cap onto an Issuing card.

    Our DB cap + stripe_authorization.decide_authorization decides synchronous
    approvals. But Stripe also enforces spending_limits on the card itself at
    its edge — if the DB cap is raised without pushing here, the real merchant
    transaction will still decline. Called from the approval "raise cap" flow
    and any manual cap change.
    """
    await _update_spending_limits(
        account_id=account_id,
        card_id=card_id,
        weekly_cents=weekly_spend_cap_cents,
        per_auth_cents=None,
    )


async def update_issuing_caps(
    account_id: str,
    card_id: str,
    weekly_spend_cap_cents: int,
    per_auth_cap_cents: int,
) -> None:
    """Push both the weekly and per-authorization caps onto the Issuing card.

    Stripe takes a single spending_limits list — we rebuild it with both
    intervals every time so the card's view stays a mirror of the business row.
    """
    await _update_spending_limits(
        account_id=account_id,
        card_id=card_id,
        weekly_cents=weekly_spend_cap_cents,
        per_auth_cents=per_auth_cap_cents,
    )


async def _update_spending_limits(
    *,
    account_id: str,
    card_id: str,
    weekly_cents: int,
    per_auth_cents: int | None,
) -> None:
    settings = get_settings()
    if not settings.stripe_issuing_enabled:
        raise RuntimeError("Issuing not yet enabled")
    s = _configured_stripe()

    limits: list[dict[str, Any]] = [{"amount": weekly_cents, "interval": "weekly"}]
    if per_auth_cents is not None:
        limits.append({"amount": per_auth_cents, "interval": "per_authorization"})

    def _update() -> None:
        s.issuing.Card.modify(
            card_id,
            stripe_account=account_id,
            spending_controls={"spending_limits": limits},
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

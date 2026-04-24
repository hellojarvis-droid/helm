"""Top-up pricing math — how much Stripe charges so the user nets
exactly `credit_amount_cents` in credits.

**Transparent-fee contract (user-confirmed decision):** when a user
asks for $X of credits they receive exactly $X. The Stripe processing
fee is charged on top, labeled explicitly on the checkout page and in
the UI preview ("Stripe processing: $0.88 — card-network fees, not
Helm"). Helm nets ~0 on the fee leg; we only mark up the credit-usage
downstream.

Two payment methods today:

    **card** — Stripe's standard 2.9% + $0.30. The fee is computed on
    the **total** charged, which includes the fee itself, so the
    solution is recursive: we invert the formula and round up.

    **us_bank_account** — Stripe ACH via Financial Connections at
    0.8% capped at $5.00. Same recursive inversion.

The fee estimator is pure and deterministic so the UI preview and the
Stripe session creation agree to the cent.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Literal

PaymentMethod = Literal["card", "us_bank_account"]

# Stripe's posted rates. Kept here (not hard-coded in routes) so if
# Stripe changes them we flip one constant.
_CARD_PCT = 0.029
_CARD_FIXED_CENTS = 30  # $0.30

_ACH_PCT = 0.008
_ACH_CAP_CENTS = 500  # $5.00 cap


@dataclass(frozen=True, slots=True)
class TopUpQuote:
    """The numbers the UI previews BEFORE clicking Buy. Every field is
    in cents to match the rest of the credits subsystem."""

    credit_amount_cents: int  # what lands in the user's balance
    fee_cents: int  # Stripe fee (card networks, not Helm)
    total_charge_cents: int  # what Stripe will charge the card/bank
    method: PaymentMethod
    # Helm-side economic note — for internal dashboards, never shown
    # to the user. Near-zero by design; non-zero only when rounding
    # goes our way by a cent or two.
    helm_margin_on_fee_cents: int


def quote(*, credit_amount_cents: int, method: PaymentMethod) -> TopUpQuote:
    """Compute the exact charge for a requested credit amount.

    Invariant: after Stripe takes its fee, Helm receives at least
    `credit_amount_cents`. We ceil() to satisfy this — any rounding
    residue (≤1¢) is tracked in `helm_margin_on_fee_cents` for
    bookkeeping.
    """
    if credit_amount_cents <= 0:
        raise ValueError("credit_amount_cents must be > 0")

    if method == "card":
        # Recursive: total = credit + total*0.029 + 30, so
        # total = (credit + 30) / (1 - 0.029).
        total = ceil((credit_amount_cents + _CARD_FIXED_CENTS) / (1 - _CARD_PCT))
    elif method == "us_bank_account":
        # Uncapped: total = credit / (1 - 0.008). Then check the cap —
        # if the uncapped fee would exceed $5, fall back to flat-cap math.
        uncapped_total = ceil(credit_amount_cents / (1 - _ACH_PCT))
        uncapped_fee = uncapped_total - credit_amount_cents
        if uncapped_fee > _ACH_CAP_CENTS:
            total = credit_amount_cents + _ACH_CAP_CENTS
        else:
            total = uncapped_total
    else:
        raise ValueError(f"unknown method: {method}")

    fee = total - credit_amount_cents
    actual_stripe_fee = _actual_stripe_fee(method, total)
    # The margin is (what we charged the user as fee) - (what Stripe
    # actually takes). With ceil-rounding this is 0 or 1 cent.
    margin = fee - actual_stripe_fee

    return TopUpQuote(
        credit_amount_cents=credit_amount_cents,
        fee_cents=fee,
        total_charge_cents=total,
        method=method,
        helm_margin_on_fee_cents=margin,
    )


def _actual_stripe_fee(method: PaymentMethod, total_cents: int) -> int:
    if method == "card":
        return round(total_cents * _CARD_PCT + _CARD_FIXED_CENTS)
    if method == "us_bank_account":
        raw = round(total_cents * _ACH_PCT)
        return min(raw, _ACH_CAP_CENTS)
    raise ValueError(method)


def fee_explanation(method: PaymentMethod) -> str:
    """One-line explanation shown next to the fee in the UI preview."""
    if method == "card":
        return "Stripe card-network fee (2.9% + $0.30). Not a Helm charge."
    if method == "us_bank_account":
        return "Stripe ACH fee (0.8%, capped at $5.00). Not a Helm charge."
    raise ValueError(method)

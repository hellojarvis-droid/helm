"""Credits — the single authority for mutating `credit_balances`.

Every billable action in Helm goes through one of these five operations:

    starter_grant(user_id)
        — one-time $5 bonus for a new user. Idempotent: re-calling is a
          no-op once the starter row exists.

    subscription_grant(user_id, tier, cycle_start, cycle_end)
        — monthly tier allowance. Idempotent per (user, cycle_start)
          via the unique constraint on `subscription_grants`.

    purchase(user_id, amount_cents, stripe_ids, description)
        — a Stripe top-up settled. Adds to balance.

    reserve(user_id, estimate_cents, reference_*)
        — atomic hold before a billable action. Returns a reservation
          id the caller stashes. If the balance is insufficient, raises
          InsufficientCreditsError (route returns 402 with a prompt
          to top up).

    commit(user_id, reservation_id, actual_cents)
        — settle a reservation: book the actual debit and refund any
          unused headroom. Idempotent per reservation_id; calling
          twice is a no-op.

    refund(user_id, reservation_id, reason)
        — failure path; releases the full reservation back to the
          balance. Idempotent per reservation_id.

Atomicity: every mutation runs inside a single transaction with the
user's `credit_balances` row locked `FOR UPDATE`. Prevents lost-update
races between concurrent reserves or between a reserve and a commit.

Display convention: everywhere the user sees credits, we show dollars
(cents / 100, two decimals). Internally we stay in cents — no floats,
no rounding surprises.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from helm.db.models import CreditBalance, CreditTransaction, SubscriptionGrant

log = structlog.get_logger("helm.credits")


STARTER_GRANT_CENTS = 500  # $5 for every new user

# Sub-tier monthly allowance in cents. These are internal — the user
# never sees a dollar value attached to their tier. We show capacity
# language ("priority queue · higher throughput"). Users who run over
# the allowance top up purchased credits on top; both live in the same
# balance so rollover is automatic.
TIER_MONTHLY_GRANT_CENTS: dict[str, int] = {
    "founder": 15_000,  # ~$150 of activity covered by the $199 sub
    "operator": 40_000,  # ~$400 of activity covered by the $499 sub
    "portfolio": 150_000,  # ~$1,500 of activity covered by the $1,999 sub
}

# Minimum top-up (in cents) users can purchase.
MIN_TOP_UP_CENTS = 2_000  # $20


# ────────────────────────────────────────────────────────────────────
# Errors
# ────────────────────────────────────────────────────────────────────


class InsufficientCreditsError(Exception):
    """Raised by `reserve` when the user's balance can't cover the estimate.

    Route handlers translate to HTTP 402 with a payload the UI uses to
    render the "top up to continue" prompt.
    """

    def __init__(self, *, user_id: uuid.UUID, needed_cents: int, balance_cents: int) -> None:
        super().__init__(
            f"user {user_id} has {balance_cents}¢ but needs {needed_cents}¢"
        )
        self.user_id = user_id
        self.needed_cents = needed_cents
        self.balance_cents = balance_cents


class ReservationNotFoundError(Exception):
    """Commit/refund called with a reservation_id we have no record of."""


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


async def _locked_balance(db: AsyncSession, user_id: uuid.UUID) -> CreditBalance:
    """Fetch-or-create the user's balance row with a row-level lock held
    until commit. All mutations go through here — this is the reason
    concurrent reserves can't race and drop the balance below zero."""
    row_q = await db.execute(
        select(CreditBalance)
        .where(CreditBalance.user_id == user_id)
        .with_for_update()
    )
    row = row_q.scalar_one_or_none()
    if row is None:
        row = CreditBalance(user_id=user_id)
        db.add(row)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            row_q = await db.execute(
                select(CreditBalance)
                .where(CreditBalance.user_id == user_id)
                .with_for_update()
            )
            row = row_q.scalar_one()
    return row


async def _append_transaction(
    db: AsyncSession,
    *,
    balance: CreditBalance,
    kind: str,
    amount_cents: int,
    description: str,
    reservation_id: uuid.UUID | None = None,
    reference_type: str | None = None,
    reference_id: uuid.UUID | None = None,
    stripe_payment_intent_id: str | None = None,
    stripe_checkout_session_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> CreditTransaction:
    """Apply an amount to the locked balance and write the ledger row.
    Caller must already hold the balance row lock (via _locked_balance).
    """
    new_balance = balance.balance_cents + amount_cents
    if new_balance < 0:
        # Caller should have gated via balance_cents check; getting here
        # means a logic bug. Raising preserves the invariant at the DB
        # check-constraint anyway, but the explicit error is clearer.
        raise ValueError(
            f"credit operation would take balance negative: "
            f"{balance.balance_cents} + {amount_cents} = {new_balance}"
        )
    balance.balance_cents = new_balance
    balance.updated_at = datetime.now(tz=UTC)
    if amount_cents > 0:
        if kind == "purchase":
            balance.lifetime_purchased_cents += amount_cents
        elif kind in ("starter_grant", "subscription_grant", "adjustment"):
            balance.lifetime_granted_cents += amount_cents
    else:
        if kind == "commit":
            balance.lifetime_spent_cents += -amount_cents

    txn = CreditTransaction(
        user_id=balance.user_id,
        kind=kind,
        amount_cents=amount_cents,
        balance_after_cents=new_balance,
        reservation_id=reservation_id,
        reference_type=reference_type,
        reference_id=reference_id,
        stripe_payment_intent_id=stripe_payment_intent_id,
        stripe_checkout_session_id=stripe_checkout_session_id,
        description=description,
        meta=meta or {},
    )
    db.add(txn)
    await db.flush()
    return txn


# ────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────


async def balance_for(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Read-only current balance in cents. Returns 0 for users who
    haven't received any credits yet (their row doesn't exist)."""
    row_q = await db.execute(
        select(CreditBalance).where(CreditBalance.user_id == user_id)
    )
    row = row_q.scalar_one_or_none()
    return row.balance_cents if row else 0


async def starter_grant(
    db: AsyncSession, *, user_id: uuid.UUID, amount_cents: int = STARTER_GRANT_CENTS
) -> CreditTransaction | None:
    """One-time signup bonus. Idempotent: once a starter_grant row
    exists for this user, subsequent calls are no-ops."""
    existing_q = await db.execute(
        select(CreditTransaction).where(
            CreditTransaction.user_id == user_id,
            CreditTransaction.kind == "starter_grant",
        )
    )
    if existing_q.scalar_one_or_none() is not None:
        return None
    balance = await _locked_balance(db, user_id)
    return await _append_transaction(
        db,
        balance=balance,
        kind="starter_grant",
        amount_cents=amount_cents,
        description=f"Welcome — ${amount_cents / 100:.2f} of starter credits.",
    )


async def subscription_grant(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    tier: str,
    cycle_start: datetime,
    cycle_end: datetime,
    amount_cents: int | None = None,
) -> CreditTransaction | None:
    """Idempotent per (user, cycle_start) via unique constraint on
    subscription_grants. A Stripe webhook replay or clock drift won't
    double-credit."""
    cents = amount_cents if amount_cents is not None else TIER_MONTHLY_GRANT_CENTS.get(tier, 0)
    if cents <= 0:
        return None

    grant = SubscriptionGrant(
        user_id=user_id,
        tier=tier,
        cycle_start=cycle_start,
        cycle_end=cycle_end,
        amount_cents=cents,
    )
    db.add(grant)
    try:
        await db.flush()
    except IntegrityError:
        # Already granted for this cycle — idempotent no-op.
        await db.rollback()
        return None

    balance = await _locked_balance(db, user_id)
    txn = await _append_transaction(
        db,
        balance=balance,
        kind="subscription_grant",
        amount_cents=cents,
        description=(
            f"{tier.capitalize()} monthly usage — cycle {cycle_start.date().isoformat()}"
        ),
        reference_type="subscription_cycle",
        meta={
            "tier": tier,
            "cycle_start": cycle_start.isoformat(),
            "cycle_end": cycle_end.isoformat(),
        },
    )
    grant.credit_transaction_id = txn.id
    await db.flush()
    return txn


async def purchase(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount_cents: int,
    stripe_payment_intent_id: str | None = None,
    stripe_checkout_session_id: str | None = None,
    description: str | None = None,
    meta: dict[str, Any] | None = None,
) -> CreditTransaction:
    """Settle a Stripe top-up into the user's balance.

    Caller is the Stripe webhook handler — idempotency should be
    enforced upstream by deduping on the PaymentIntent id (we do it
    here too with a single SELECT for safety)."""
    if amount_cents < MIN_TOP_UP_CENTS:
        raise ValueError(
            f"top-up below minimum: {amount_cents}¢ < {MIN_TOP_UP_CENTS}¢"
        )
    if stripe_payment_intent_id:
        dup_q = await db.execute(
            select(CreditTransaction).where(
                CreditTransaction.stripe_payment_intent_id == stripe_payment_intent_id
            )
        )
        dup = dup_q.scalar_one_or_none()
        if dup is not None:
            return dup

    balance = await _locked_balance(db, user_id)
    return await _append_transaction(
        db,
        balance=balance,
        kind="purchase",
        amount_cents=amount_cents,
        description=description or f"Top-up: ${amount_cents / 100:.2f} of credits added.",
        reference_type="top_up",
        stripe_payment_intent_id=stripe_payment_intent_id,
        stripe_checkout_session_id=stripe_checkout_session_id,
        meta=meta or {},
    )


async def reserve(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    estimate_cents: int,
    reference_type: str,
    reference_id: uuid.UUID | None = None,
    description: str | None = None,
    headroom_pct: float = 0.20,
    meta: dict[str, Any] | None = None,
) -> tuple[uuid.UUID, CreditTransaction]:
    """Atomic hold for a billable action about to run.

    Reserves `estimate * (1 + headroom_pct)` from the balance so minor
    provider-side variance doesn't force a second round-trip. Returns
    `(reservation_id, txn_row)`. Callers keep the reservation_id so
    they can commit or refund later.
    """
    hold_cents = int(estimate_cents * (1.0 + headroom_pct))
    if hold_cents < 0:
        raise ValueError("estimate_cents must be >= 0")

    balance = await _locked_balance(db, user_id)
    if balance.balance_cents < hold_cents:
        raise InsufficientCreditsError(
            user_id=user_id,
            needed_cents=hold_cents,
            balance_cents=balance.balance_cents,
        )

    reservation_id = uuid.uuid4()
    txn = await _append_transaction(
        db,
        balance=balance,
        kind="reserve",
        amount_cents=-hold_cents,
        description=description or f"Reserved ${hold_cents / 100:.2f} for {reference_type}.",
        reservation_id=reservation_id,
        reference_type=reference_type,
        reference_id=reference_id,
        meta={
            **(meta or {}),
            "estimate_cents": estimate_cents,
            "headroom_pct": headroom_pct,
        },
    )
    return reservation_id, txn


async def commit(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    reservation_id: uuid.UUID,
    actual_cents: int,
    description: str | None = None,
    meta: dict[str, Any] | None = None,
) -> CreditTransaction | None:
    """Settle a reservation with the actual cost of the billable action.

    If `actual_cents < reserved`, the unused headroom is refunded in the
    same transaction. Idempotent per reservation_id: a second call is a
    no-op.
    """
    if actual_cents < 0:
        raise ValueError("actual_cents must be >= 0")

    # Idempotency gate — if a commit for this reservation already exists,
    # short-circuit.
    existing_q = await db.execute(
        select(CreditTransaction).where(
            CreditTransaction.reservation_id == reservation_id,
            CreditTransaction.kind == "commit",
        )
    )
    if existing_q.scalar_one_or_none() is not None:
        return None

    reserve_row = await _reservation_row(db, reservation_id)
    if reserve_row is None:
        raise ReservationNotFoundError(str(reservation_id))
    held_cents = -reserve_row.amount_cents  # reserve was negative

    balance = await _locked_balance(db, user_id)

    # Debit the actual cost (if any), then refund the unused portion so
    # the net over reserve+commit(+refund) equals -actual_cents.
    commit_txn: CreditTransaction | None = None
    if actual_cents > 0:
        commit_txn = await _append_transaction(
            db,
            balance=balance,
            kind="commit",
            amount_cents=-actual_cents,
            description=description
            or f"Used ${actual_cents / 100:.2f} on {reserve_row.reference_type or 'action'}.",
            reservation_id=reservation_id,
            reference_type=reserve_row.reference_type,
            reference_id=reserve_row.reference_id,
            meta=meta or {},
        )

    unused = held_cents - actual_cents
    if unused > 0:
        # Refund the unused headroom.
        await _append_transaction(
            db,
            balance=balance,
            kind="refund",
            amount_cents=unused,
            description=f"Refund: unused reservation headroom (${unused / 100:.2f}).",
            reservation_id=reservation_id,
            reference_type=reserve_row.reference_type,
            reference_id=reserve_row.reference_id,
        )

    return commit_txn


async def refund(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    reservation_id: uuid.UUID,
    reason: str,
) -> CreditTransaction | None:
    """Release a reservation back to the balance in full.

    Called on any failure path (render failed, upstream provider errored,
    user cancelled mid-flight). Idempotent: if commit or refund already
    ran for this reservation, no-op.
    """
    done_q = await db.execute(
        select(CreditTransaction).where(
            CreditTransaction.reservation_id == reservation_id,
            CreditTransaction.kind.in_(("commit", "refund")),
        )
    )
    if done_q.scalar_one_or_none() is not None:
        return None

    reserve_row = await _reservation_row(db, reservation_id)
    if reserve_row is None:
        raise ReservationNotFoundError(str(reservation_id))
    held_cents = -reserve_row.amount_cents

    balance = await _locked_balance(db, user_id)
    return await _append_transaction(
        db,
        balance=balance,
        kind="refund",
        amount_cents=held_cents,
        description=f"Refund (${held_cents / 100:.2f}): {reason}",
        reservation_id=reservation_id,
        reference_type=reserve_row.reference_type,
        reference_id=reserve_row.reference_id,
        meta={"reason": reason},
    )


async def adjustment(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    amount_cents: int,
    reason: str,
    actor: str = "operator",
) -> CreditTransaction:
    """Operator-issued correction — customer support, promotional
    credits, mis-charge refund, etc. Recorded with `actor` in meta so
    audits can trace who authorized what."""
    balance = await _locked_balance(db, user_id)
    return await _append_transaction(
        db,
        balance=balance,
        kind="adjustment",
        amount_cents=amount_cents,
        description=f"Adjustment: {reason}",
        reference_type="adjustment",
        meta={"actor": actor, "reason": reason},
    )


async def _reservation_row(
    db: AsyncSession, reservation_id: uuid.UUID
) -> CreditTransaction | None:
    row_q = await db.execute(
        select(CreditTransaction)
        .where(
            CreditTransaction.reservation_id == reservation_id,
            CreditTransaction.kind == "reserve",
        )
        .limit(1)
    )
    return row_q.scalar_one_or_none()

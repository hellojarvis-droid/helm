"""Credits REST endpoints — balance, history, top-up quotes, checkout.

All tenant-scoped to the current user via `require_user`.

    GET  /credits/balance         — current balance + lifetime totals +
                                    starter-grant status for the UI chip.
    GET  /credits/transactions    — paginated ledger for /billing history.
    POST /credits/top_up/quote    — fee + total preview BEFORE checkout
                                    (no side effects). UI polls this on
                                    every amount or method change.
    POST /credits/top_up          — creates a Stripe Checkout session for
                                    the picked amount + method. Returns
                                    the hosted-checkout URL.

The `checkout.session.completed` webhook in routes/webhooks.py is the
other half of the top-up path: it reads the metadata we stamped here
and calls `credits.purchase()` to settle the balance.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.config import get_settings
from helm.db.models import CreditBalance, CreditTransaction
from helm.db.session import get_session
from helm.services import credits, credits_pricing, stripe_client
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(prefix="/credits", tags=["credits"])


class BalanceResponse(BaseModel):
    balance_cents: int
    lifetime_granted_cents: int
    lifetime_purchased_cents: int
    lifetime_spent_cents: int
    starter_granted: bool
    min_top_up_cents: int


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> BalanceResponse:
    """Current balance + lifetime totals. First call for a brand-new user
    also drops the $5 starter grant so the UI never sees a zero balance
    for an authed user who hasn't topped up yet."""
    user_row = await sync_user_from_supabase(db, user)

    # Issue the one-time starter grant on first read. Idempotent.
    txn = await credits.starter_grant(db, user_id=user_row.id)
    starter_granted = txn is not None or await _has_starter_grant(db, user_row.id)
    if txn is not None:
        await db.commit()

    bal_q = await db.execute(
        select(CreditBalance).where(CreditBalance.user_id == user_row.id)
    )
    bal = bal_q.scalar_one_or_none()
    return BalanceResponse(
        balance_cents=bal.balance_cents if bal else 0,
        lifetime_granted_cents=bal.lifetime_granted_cents if bal else 0,
        lifetime_purchased_cents=bal.lifetime_purchased_cents if bal else 0,
        lifetime_spent_cents=bal.lifetime_spent_cents if bal else 0,
        starter_granted=starter_granted,
        min_top_up_cents=credits.MIN_TOP_UP_CENTS,
    )


class TransactionResponse(BaseModel):
    id: uuid.UUID
    kind: str
    amount_cents: int
    balance_after_cents: int
    reservation_id: uuid.UUID | None
    reference_type: str | None
    reference_id: uuid.UUID | None
    description: str
    created_at: datetime
    meta: dict[str, Any]


@router.get("/transactions", response_model=list[TransactionResponse])
async def list_transactions(
    kind: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before_id: uuid.UUID | None = None,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[TransactionResponse]:
    user_row = await sync_user_from_supabase(db, user)
    q = select(CreditTransaction).where(CreditTransaction.user_id == user_row.id)
    if kind:
        q = q.where(CreditTransaction.kind == kind)
    if before_id is not None:
        anchor = await db.get(CreditTransaction, before_id)
        if anchor is not None:
            q = q.where(CreditTransaction.created_at < anchor.created_at)
    q = q.order_by(CreditTransaction.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [
        TransactionResponse(
            id=r.id,
            kind=r.kind,
            amount_cents=r.amount_cents,
            balance_after_cents=r.balance_after_cents,
            reservation_id=r.reservation_id,
            reference_type=r.reference_type,
            reference_id=r.reference_id,
            description=r.description,
            created_at=r.created_at,
            meta=r.meta,
        )
        for r in rows
    ]


async def _has_starter_grant(db: AsyncSession, user_id: uuid.UUID) -> bool:
    row_q = await db.execute(
        select(CreditTransaction).where(
            CreditTransaction.user_id == user_id,
            CreditTransaction.kind == "starter_grant",
        )
    )
    return row_q.scalar_one_or_none() is not None


# ──────────────────────────────────────────────────────────────
# Top-up — quote + checkout creation
# ──────────────────────────────────────────────────────────────


PaymentMethodT = Literal["card", "us_bank_account"]


class TopUpQuoteRequest(BaseModel):
    credit_amount_cents: Annotated[int, Field(ge=credits.MIN_TOP_UP_CENTS, le=10_000_000)]
    payment_method: PaymentMethodT = "card"


class TopUpQuoteResponse(BaseModel):
    credit_amount_cents: int
    fee_cents: int
    total_charge_cents: int
    payment_method: PaymentMethodT
    fee_explanation: str


@router.post("/top_up/quote", response_model=TopUpQuoteResponse)
async def top_up_quote(
    body: TopUpQuoteRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> TopUpQuoteResponse:
    """Preview the exact Stripe charge for a requested credit amount.

    Side-effect-free: no DB writes. The UI calls this on every amount
    or method change to show the live breakdown. We still auth-gate so
    the fee math doesn't leak to anonymous traffic.
    """
    await sync_user_from_supabase(db, user)
    q = credits_pricing.quote(
        credit_amount_cents=body.credit_amount_cents,
        method=body.payment_method,
    )
    return TopUpQuoteResponse(
        credit_amount_cents=q.credit_amount_cents,
        fee_cents=q.fee_cents,
        total_charge_cents=q.total_charge_cents,
        payment_method=q.method,
        fee_explanation=credits_pricing.fee_explanation(q.method),
    )


class TopUpStartRequest(BaseModel):
    credit_amount_cents: Annotated[int, Field(ge=credits.MIN_TOP_UP_CENTS, le=10_000_000)]
    payment_method: PaymentMethodT = "card"


class TopUpStartResponse(BaseModel):
    url: str
    credit_amount_cents: int
    fee_cents: int
    total_charge_cents: int


@router.post("/top_up", response_model=TopUpStartResponse)
async def top_up(
    body: TopUpStartRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> TopUpStartResponse:
    """Create a Stripe Checkout session for the user's top-up. Returns
    the hosted-checkout URL; the UI full-page redirects to it. Credit
    lands via the `checkout.session.completed` webhook handler."""
    user_row = await sync_user_from_supabase(db, user)
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=503,
            detail="Stripe isn't configured on this deployment yet",
        )

    q = credits_pricing.quote(
        credit_amount_cents=body.credit_amount_cents,
        method=body.payment_method,
    )

    web = settings.web_base_url.rstrip("/")
    success_url = f"{web}/billing?topup=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{web}/billing?topup=cancel"

    try:
        url = await stripe_client.create_credits_checkout_session(
            user_id=str(user_row.id),
            credit_amount_cents=q.credit_amount_cents,
            fee_cents=q.fee_cents,
            total_charge_cents=q.total_charge_cents,
            payment_method=q.method,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"stripe checkout create failed: {e!s}",
        ) from e

    return TopUpStartResponse(
        url=url,
        credit_amount_cents=q.credit_amount_cents,
        fee_cents=q.fee_cents,
        total_charge_cents=q.total_charge_cents,
    )

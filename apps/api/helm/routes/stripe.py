"""Stripe Connect onboarding + status — Phase 2 Session 7 surface.

`POST /businesses/{id}/stripe/onboard` kicks off (or resumes) the Connect
Custom onboarding for a business. Idempotent: if an account already exists,
we just mint a fresh onboarding link for it.

`GET /businesses/{id}/stripe/status` reads the current state without
touching Stripe — webhooks keep `stripe_onboarding_complete` in sync.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.config import get_settings
from helm.db.session import get_session
from helm.db.tenant import get_business_for_user
from helm.services import stripe_client
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(prefix="/businesses", tags=["stripe"])


class OnboardResponse(BaseModel):
    account_id: str
    onboarding_url: str
    expires_at: int
    reused_existing_account: bool


class StripeStatusResponse(BaseModel):
    account_id: str | None
    onboarding_complete: bool
    cardholder_id: str | None
    card_id: str | None


class ProvisionResponse(BaseModel):
    business_id: str
    cardholder_id: str
    card_id: str
    reused_existing: bool


@router.post("/{business_id}/stripe/onboard", response_model=OnboardResponse)
async def onboard(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> OnboardResponse:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    settings = get_settings()
    base = settings.api_base_url.rstrip("/")
    return_url = f"{base}/businesses/{business_id}/stripe/callback?status=return"
    refresh_url = f"{base}/businesses/{business_id}/stripe/callback?status=refresh"

    reused = False
    if biz.stripe_account_id:
        account_id = biz.stripe_account_id
        reused = True
    else:
        account_id = await stripe_client.create_connect_account(
            business_name=biz.name,
            business_email=user_row.email,
        )
        biz.stripe_account_id = account_id
        await db.commit()

    try:
        link = await stripe_client.create_account_link(
            account_id=account_id,
            return_url=return_url,
            refresh_url=refresh_url,
        )
    except Exception as e:  # Stripe.error or wrapper RuntimeError
        raise HTTPException(status_code=502, detail=f"stripe onboarding link failed: {e!s}") from e

    return OnboardResponse(
        account_id=account_id,
        onboarding_url=link.onboarding_url,
        expires_at=link.expires_at,
        reused_existing_account=reused,
    )


@router.get("/{business_id}/stripe/status", response_model=StripeStatusResponse)
async def status(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> StripeStatusResponse:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    return StripeStatusResponse(
        account_id=biz.stripe_account_id,
        onboarding_complete=biz.stripe_onboarding_complete,
        cardholder_id=biz.stripe_issuing_cardholder_id,
        card_id=biz.stripe_card_id,
    )


@router.post(
    "/{business_id}/stripe/issuing/provision",
    response_model=ProvisionResponse,
)
async def provision_issuing(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> ProvisionResponse:
    """Create a Stripe Issuing cardholder + virtual card for this business.

    Hard preconditions (no bypass):
      1. STRIPE_ISSUING_ENABLED=true — we don't create real card numbers on
         a project that hasn't passed Issuing-for-Agents underwriting.
      2. Connect account onboarding must be complete — Stripe refuses
         issuance against an unfinished connected account.
      3. Idempotent: if a cardholder+card pair already exists, return it.

    Spending controls are applied at card creation so Stripe enforces the
    weekly cap + MCC allowlist at the authorization layer. Our in-process
    `stripe_authorization.decide_authorization` is belt-and-braces.
    """
    settings = get_settings()
    if not settings.stripe_issuing_enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "Issuing is not enabled (STRIPE_ISSUING_ENABLED=false). Flip on "
                "after the Issuing-for-Agents underwriting approval lands."
            ),
        )

    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    if not biz.stripe_account_id:
        raise HTTPException(
            status_code=409,
            detail="stripe account must be created first (POST /stripe/onboard)",
        )
    if not biz.stripe_onboarding_complete:
        raise HTTPException(
            status_code=409,
            detail="stripe onboarding must complete before issuing can be provisioned",
        )

    if biz.stripe_issuing_cardholder_id and biz.stripe_card_id:
        return ProvisionResponse(
            business_id=str(biz.id),
            cardholder_id=biz.stripe_issuing_cardholder_id,
            card_id=biz.stripe_card_id,
            reused_existing=True,
        )

    # Default MCC allowlist — same as services/stripe_authorization so our
    # in-process check and Stripe's side stay in sync.
    from helm.services.stripe_authorization import _DEFAULT_MCC_ALLOWLIST

    cardholder_id = biz.stripe_issuing_cardholder_id
    if not cardholder_id:
        try:
            cardholder_id = await stripe_client.create_issuing_cardholder(
                account_id=biz.stripe_account_id,
                business_name=biz.name,
                business_email=user_row.email,
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"stripe cardholder create: {e!s}") from e
        biz.stripe_issuing_cardholder_id = cardholder_id
        await db.commit()

    try:
        card_id = await stripe_client.create_issuing_card(
            account_id=biz.stripe_account_id,
            cardholder_id=cardholder_id,
            weekly_spend_cap_cents=biz.weekly_spend_cap_cents,
            allowed_mcc_codes=sorted(_DEFAULT_MCC_ALLOWLIST),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"stripe card create: {e!s}") from e

    biz.stripe_card_id = card_id
    await db.commit()

    return ProvisionResponse(
        business_id=str(biz.id),
        cardholder_id=cardholder_id,
        card_id=card_id,
        reused_existing=False,
    )

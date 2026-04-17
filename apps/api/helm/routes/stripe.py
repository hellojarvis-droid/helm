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
    )

"""Brand Library REST routes.

    GET    /businesses/{id}/brand_library        — read
    PUT    /businesses/{id}/brand_library        — upsert (edit form save)
    POST   /businesses/{id}/brand_library/scrape — LLM-scrape a URL and
                                                   return the parsed
                                                   fields WITHOUT saving
                                                   (user reviews first)

The scrape endpoint debits the user's credit balance for the LLM call.
If balance is insufficient, returns 402 with a prompt to top up.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.models import BrandLibrary
from helm.db.session import get_session
from helm.db.tenant import get_business_for_user
from helm.errors import ClientError
from helm.services import brand_library, credits
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(tags=["brand_library"])


# ──────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────


class BrandLibraryResponse(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    tagline: str | None
    source_url: str | None
    palette: dict[str, Any]
    typography: dict[str, Any]
    logos: list[dict[str, Any]]
    voice_paragraph: str | None
    banned_phrases: list[str]
    winning_references: list[dict[str, Any]]
    moodboard_urls: list[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: BrandLibrary) -> BrandLibraryResponse:
        return cls(
            id=row.id,
            business_id=row.business_id,
            name=row.name,
            tagline=row.tagline,
            source_url=row.source_url,
            palette=dict(row.palette),
            typography=dict(row.typography),
            logos=list(row.logos),
            voice_paragraph=row.voice_paragraph,
            banned_phrases=list(row.banned_phrases),
            winning_references=list(row.winning_references),
            moodboard_urls=list(row.moodboard_urls),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class UpsertBrandLibraryRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=160)]
    tagline: Annotated[str | None, Field(max_length=500)] = None
    source_url: Annotated[str | None, Field(max_length=500)] = None
    palette: dict[str, Any] = Field(default_factory=dict)
    typography: dict[str, Any] = Field(default_factory=dict)
    logos: list[dict[str, Any]] = Field(default_factory=list)
    voice_paragraph: Annotated[str | None, Field(max_length=2000)] = None
    banned_phrases: list[str] = Field(default_factory=list)
    winning_references: list[dict[str, Any]] = Field(default_factory=list)
    moodboard_urls: list[str] = Field(default_factory=list)


class ScrapeRequest(BaseModel):
    url: HttpUrl


class ScrapeResponse(BaseModel):
    """Returned by /scrape — the user reviews + edits before saving."""

    source_url: str
    extracted: dict[str, Any]


# ──────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────


@router.get(
    "/businesses/{business_id}/brand_library",
    response_model=BrandLibraryResponse,
)
async def get_brand_library(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> BrandLibraryResponse:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    row = await brand_library.get_for_business(db, business_id=business_id)
    if row is None:
        raise HTTPException(status_code=404, detail="no brand library yet")
    return BrandLibraryResponse.from_row(row)


@router.put(
    "/businesses/{business_id}/brand_library",
    response_model=BrandLibraryResponse,
)
async def upsert_brand_library(
    business_id: uuid.UUID,
    body: UpsertBrandLibraryRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> BrandLibraryResponse:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    row = await brand_library.upsert(
        db,
        business_id=business_id,
        fields=body.model_dump(),
    )
    await db.commit()
    await db.refresh(row)
    return BrandLibraryResponse.from_row(row)


@router.post(
    "/businesses/{business_id}/brand_library/scrape",
    response_model=ScrapeResponse,
)
async def scrape_brand_library(
    business_id: uuid.UUID,
    body: ScrapeRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> ScrapeResponse:
    """LLM-scrape the URL into structured brand attributes. Does NOT
    save — the client receives the extracted fields, user edits them
    in the Brand Library form, then calls PUT to persist.
    """
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    try:
        parsed = await brand_library.scrape_url(
            db,
            user_id=user_row.id,
            business_id=business_id,
            url=str(body.url),
        )
    except credits.InsufficientCreditsError as e:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "needed_cents": e.needed_cents,
                "balance_cents": e.balance_cents,
                "message": "Top up credits to continue.",
            },
        ) from e
    except brand_library.BrandScrapeFailedError as e:
        raise ClientError(
            "brand_scrape_failed",
            status_code=502,
            message=(
                "We couldn't analyze that URL. Check it's publicly accessible "
                "and try again."
            ),
        ) from e

    return ScrapeResponse(source_url=str(body.url), extracted=parsed)

"""Campaign + Master Creative read/write routes.

Auto-DAG generation is retired — Creative Studio is now a per-tool
Canvas surface (see routes/generations.py). Campaigns and master
creatives remain as the *curation* layer used by Marketing Studio to
bundle generations into a finished ad + schedule + reformat.

    POST /businesses/{id}/campaigns         — create campaign
    GET  /businesses/{id}/campaigns         — list campaigns
    POST /campaigns/{id}/creatives          — create empty master creative
                                              (curator assembles shots
                                              from Library generations)
    GET  /campaigns/{id}/creatives          — list creatives
    GET  /creatives/{id}                    — creative detail
    GET  /creatives/{id}/shots              — shot rows
    PATCH /creatives/{id}                   — edit top-level copy/title
    GET  /businesses/{id}/creatives         — library across campaigns
    POST /businesses/{id}/creatives/import  — import existing ad URL
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.models import Campaign, MasterCreative, Shot
from helm.db.session import get_session
from helm.db.tenant import get_business_for_user
from helm.errors import upstream_unavailable
from helm.services import ad_importer, credits
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(tags=["creatives"])


# ──────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────


class CampaignResponse(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    goal: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class CreateCampaignRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    goal: str | None = Field(default=None, max_length=1000)


class MasterCreativeResponse(BaseModel):
    model_config = {"populate_by_name": True}

    id: uuid.UUID
    campaign_id: uuid.UUID
    brief_id: uuid.UUID | None
    title: str
    canonical_aspect: str
    status: str
    copy_data: dict[str, Any] = Field(alias="copy", serialization_alias="copy")
    timeline_json: dict[str, Any] | None
    canonical_output_url: str | None
    thumbnail_url: str | None
    imported: bool
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class ShotResponse(BaseModel):
    id: uuid.UUID
    master_creative_id: uuid.UUID
    shot_order: int
    provider: str
    prompt: str
    duration_seconds: int
    options: dict[str, Any]
    status: str
    output_url: str | None
    thumbnail_url: str | None
    cost_cents: int | None
    error: str | None


class CreateCreativeRequest(BaseModel):
    """Curator creates an empty master creative; assembly happens by
    attaching Library generations as shots via the Marketing Studio UI."""

    title: str = Field(min_length=1, max_length=200)
    aspect_ratio: str = Field(default="9:16", pattern=r"^(9:16|1:1|16:9|4:5)$")


class PatchCreativeRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    headline: str | None = Field(default=None, max_length=160)
    subhead: str | None = Field(default=None, max_length=500)
    cta: str | None = Field(default=None, max_length=120)
    caption_meta: str | None = Field(default=None, max_length=2000)
    caption_tiktok: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = None


class ImportCreativeRequest(BaseModel):
    campaign_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    video_url: str = Field(min_length=1, max_length=2000)
    description: str | None = Field(default=None, max_length=2000)
    aspect_ratio: str = Field(default="9:16", pattern=r"^(9:16|1:1|16:9|4:5)$")
    transcribe: bool = True


# ──────────────────────────────────────────────────────────
# Campaigns
# ──────────────────────────────────────────────────────────


@router.post(
    "/businesses/{business_id}/campaigns",
    response_model=CampaignResponse,
    status_code=201,
)
async def create_campaign(
    business_id: uuid.UUID,
    body: CreateCampaignRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> CampaignResponse:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    row = Campaign(business_id=business_id, name=body.name.strip(), goal=body.goal)
    db.add(row)
    await db.flush()
    await db.commit()
    await db.refresh(row)
    return CampaignResponse.model_validate(row, from_attributes=True)


@router.get(
    "/businesses/{business_id}/campaigns",
    response_model=list[CampaignResponse],
)
async def list_campaigns(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[CampaignResponse]:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    q = await db.execute(
        select(Campaign)
        .where(Campaign.business_id == business_id)
        .order_by(Campaign.created_at.desc())
    )
    return [
        CampaignResponse.model_validate(row, from_attributes=True)
        for row in q.scalars().all()
    ]


# ──────────────────────────────────────────────────────────
# Creatives
# ──────────────────────────────────────────────────────────


async def _campaign_for_user(
    db: AsyncSession, user_id: uuid.UUID, campaign_id: uuid.UUID
) -> Campaign:
    q = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    row = q.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    biz = await get_business_for_user(db, user_id, row.business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return row


@router.post(
    "/campaigns/{campaign_id}/creatives",
    response_model=MasterCreativeResponse,
    status_code=201,
)
async def create_creative(
    campaign_id: uuid.UUID,
    body: CreateCreativeRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> MasterCreativeResponse:
    """Curator creates an empty master creative. The Marketing Studio UI
    attaches Library generations as shots. No automatic LLM-driven
    generation happens here anymore."""
    user_row = await sync_user_from_supabase(db, user)
    await _campaign_for_user(db, user_row.id, campaign_id)
    row = MasterCreative(
        campaign_id=campaign_id,
        title=body.title.strip(),
        canonical_aspect=body.aspect_ratio,
        status="drafting",
        copy={"copy": {}},
        tags=[],
    )
    db.add(row)
    await db.flush()
    await db.commit()
    await db.refresh(row)
    return MasterCreativeResponse.model_validate(row, from_attributes=True)


@router.get(
    "/campaigns/{campaign_id}/creatives",
    response_model=list[MasterCreativeResponse],
)
async def list_creatives(
    campaign_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[MasterCreativeResponse]:
    user_row = await sync_user_from_supabase(db, user)
    await _campaign_for_user(db, user_row.id, campaign_id)
    q = await db.execute(
        select(MasterCreative)
        .where(MasterCreative.campaign_id == campaign_id)
        .order_by(MasterCreative.created_at.desc())
    )
    return [
        MasterCreativeResponse.model_validate(row, from_attributes=True)
        for row in q.scalars().all()
    ]


async def _creative_for_user(
    db: AsyncSession, user_id: uuid.UUID, creative_id: uuid.UUID
) -> MasterCreative:
    row = await db.get(MasterCreative, creative_id)
    if row is None:
        raise HTTPException(status_code=404, detail="creative not found")
    campaign = await db.get(Campaign, row.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="creative not found")
    biz = await get_business_for_user(db, user_id, campaign.business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="creative not found")
    return row


@router.get(
    "/creatives/{creative_id}",
    response_model=MasterCreativeResponse,
)
async def get_creative(
    creative_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> MasterCreativeResponse:
    user_row = await sync_user_from_supabase(db, user)
    row = await _creative_for_user(db, user_row.id, creative_id)
    return MasterCreativeResponse.model_validate(row, from_attributes=True)


@router.get(
    "/creatives/{creative_id}/shots",
    response_model=list[ShotResponse],
)
async def list_shots(
    creative_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[ShotResponse]:
    user_row = await sync_user_from_supabase(db, user)
    await _creative_for_user(db, user_row.id, creative_id)
    q = await db.execute(
        select(Shot)
        .where(Shot.master_creative_id == creative_id)
        .order_by(Shot.shot_order.asc())
    )
    return [
        ShotResponse.model_validate(row, from_attributes=True)
        for row in q.scalars().all()
    ]


@router.patch(
    "/creatives/{creative_id}",
    response_model=MasterCreativeResponse,
)
async def patch_creative(
    creative_id: uuid.UUID,
    body: PatchCreativeRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> MasterCreativeResponse:
    user_row = await sync_user_from_supabase(db, user)
    row = await _creative_for_user(db, user_row.id, creative_id)

    if body.title is not None:
        row.title = body.title.strip()
    if body.tags is not None:
        row.tags = [t.strip() for t in body.tags if t.strip()]

    copy_bundle = dict(row.copy or {})
    copy_section = dict(copy_bundle.get("copy") or {})
    for field, value in {
        "headline": body.headline,
        "subhead": body.subhead,
        "cta": body.cta,
        "caption_meta": body.caption_meta,
        "caption_tiktok": body.caption_tiktok,
    }.items():
        if value is not None:
            copy_section[field] = value
    copy_bundle["copy"] = copy_section
    row.copy = copy_bundle

    await db.commit()
    await db.refresh(row)
    return MasterCreativeResponse.model_validate(row, from_attributes=True)


@router.get(
    "/businesses/{business_id}/creatives",
    response_model=list[MasterCreativeResponse],
)
async def list_library(
    business_id: uuid.UUID,
    q: str | None = None,
    status: str | None = None,
    aspect: str | None = None,
    limit: int = 200,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[MasterCreativeResponse]:
    """Library view — every master creative across campaigns."""
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")

    stmt = (
        select(MasterCreative)
        .join(Campaign, Campaign.id == MasterCreative.campaign_id)
        .where(Campaign.business_id == business_id)
        .order_by(MasterCreative.created_at.desc())
        .limit(max(1, min(limit, 500)))
    )
    if status:
        stmt = stmt.where(MasterCreative.status == status)
    if aspect:
        stmt = stmt.where(MasterCreative.canonical_aspect == aspect)
    if q:
        stmt = stmt.where(MasterCreative.title.ilike(f"%{q.strip()}%"))
    rows = list((await db.execute(stmt)).scalars().all())
    return [MasterCreativeResponse.model_validate(r, from_attributes=True) for r in rows]


@router.post(
    "/businesses/{business_id}/creatives/import",
    response_model=MasterCreativeResponse,
    status_code=201,
)
async def import_creative(
    business_id: uuid.UUID,
    body: ImportCreativeRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> MasterCreativeResponse:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    campaign = await _campaign_for_user(db, user_row.id, body.campaign_id)
    if campaign.business_id != business_id:
        raise HTTPException(
            status_code=400, detail="campaign does not belong to business"
        )
    try:
        creative = await ad_importer.import_existing(
            db,
            user_id=user_row.id,
            business_id=business_id,
            campaign_id=body.campaign_id,
            video_url=body.video_url,
            title=body.title,
            description=body.description,
            aspect_ratio=body.aspect_ratio,
            transcribe=body.transcribe,
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
    except ad_importer.ImportFailedError as e:
        raise upstream_unavailable("The ad-import service") from e
    await db.commit()
    await db.refresh(creative)
    return MasterCreativeResponse.model_validate(creative, from_attributes=True)

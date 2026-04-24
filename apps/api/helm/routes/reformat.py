"""Reformat REST routes.

    GET  /creatives/{id}/formats       — list existing FormatRender rows
    POST /creatives/{id}/reformat      — fan out to N target formats
    GET  /businesses/{id}/format_prefs — suggested target sets from history
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
from helm.db.models import Campaign, FormatRender, MasterCreative
from helm.db.session import get_session
from helm.db.tenant import get_business_for_user
from helm.errors import ClientError
from helm.services import reformat
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(tags=["reformat"])


class FormatRenderResponse(BaseModel):
    id: uuid.UUID
    master_creative_id: uuid.UUID
    platform: str
    aspect: str
    mode: str
    status: str
    output_url: str | None
    thumbnail_url: str | None
    platform_copy: dict[str, Any]
    cost_cents: int | None
    error: str | None
    created_at: datetime


class ReformatTarget(BaseModel):
    platform: str = Field(min_length=1, max_length=40)
    aspect: str = Field(pattern=r"^(9:16|1:1|16:9|4:5)$")
    mode: str = Field(default="video", pattern=r"^(video|image|carousel)$")


class ReformatRequest(BaseModel):
    targets: list[ReformatTarget]


async def _creative_for_user(
    db: AsyncSession, user_id: uuid.UUID, creative_id: uuid.UUID
) -> MasterCreative:
    creative = await db.get(MasterCreative, creative_id)
    if creative is None:
        raise HTTPException(status_code=404, detail="creative not found")
    campaign = await db.get(Campaign, creative.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="creative not found")
    biz = await get_business_for_user(db, user_id, campaign.business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="creative not found")
    return creative


@router.get(
    "/creatives/{creative_id}/formats",
    response_model=list[FormatRenderResponse],
)
async def list_formats(
    creative_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[FormatRenderResponse]:
    user_row = await sync_user_from_supabase(db, user)
    await _creative_for_user(db, user_row.id, creative_id)
    q = await db.execute(
        select(FormatRender)
        .where(FormatRender.master_creative_id == creative_id)
        .order_by(FormatRender.created_at.desc())
    )
    return [
        FormatRenderResponse.model_validate(r, from_attributes=True)
        for r in q.scalars().all()
    ]


@router.post(
    "/creatives/{creative_id}/reformat",
    response_model=list[FormatRenderResponse],
)
async def reformat_creative(
    creative_id: uuid.UUID,
    body: ReformatRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[FormatRenderResponse]:
    user_row = await sync_user_from_supabase(db, user)
    await _creative_for_user(db, user_row.id, creative_id)

    targets = [
        {"platform": t.platform, "aspect": t.aspect, "mode": t.mode}
        for t in body.targets
    ]
    try:
        rows = await reformat.reformat(
            db,
            master_creative_id=creative_id,
            targets=targets,
        )
    except reformat.MasterNotReadyError as e:
        raise ClientError(
            "master_not_ready",
            status_code=409,
            message=str(e),
        ) from e

    await db.commit()
    refreshed: list[FormatRender] = []
    for r in rows:
        await db.refresh(r)
        refreshed.append(r)
    return [
        FormatRenderResponse.model_validate(r, from_attributes=True)
        for r in refreshed
    ]


@router.get(
    "/businesses/{business_id}/format_prefs",
    response_model=list[list[dict[str, str]]],
)
async def list_format_prefs(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[list[dict[str, str]]]:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    return await reformat.preferred_targets(db, business_id=business_id)

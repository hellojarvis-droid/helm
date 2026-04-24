"""Scheduled-post REST routes.

    POST   /creatives/{id}/schedule       — schedule publishes for one creative
    GET    /creatives/{id}/schedule       — list all scheduled posts for a creative
    GET    /businesses/{id}/schedule      — business-wide schedule view
    POST   /scheduled_posts/{id}/cancel   — cancel before publish

The scheduled-post scheduler tick publishes rows whose scheduled_at has
passed. See `services/post_scheduler.py` for lifecycle details.
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
from helm.db.models import Campaign, MasterCreative, ScheduledPost
from helm.db.session import get_session
from helm.db.tenant import get_business_for_user
from helm.errors import ClientError
from helm.services import post_scheduler
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(tags=["scheduled_posts"])


class ScheduledPostResponse(BaseModel):
    id: uuid.UUID
    master_creative_id: uuid.UUID
    business_id: uuid.UUID
    platform: str
    aspect: str
    scheduled_at: datetime
    status: str
    caption: str
    video_url: str | None
    thumbnail_url: str | None
    meta: dict[str, Any]
    external_post_id: str | None
    external_post_url: str | None
    error: str | None
    published_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime


class ScheduleTarget(BaseModel):
    platform: str = Field(min_length=1, max_length=40)
    aspect: str = Field(pattern=r"^(9:16|1:1|16:9|4:5)$")
    caption: str | None = Field(default=None, max_length=2000)


class ScheduleRequest(BaseModel):
    scheduled_at: datetime
    targets: list[ScheduleTarget]
    require_approval: bool = False


async def _creative_for_user(
    db: AsyncSession, user_id: uuid.UUID, creative_id: uuid.UUID
) -> tuple[MasterCreative, Campaign]:
    creative = await db.get(MasterCreative, creative_id)
    if creative is None:
        raise HTTPException(status_code=404, detail="creative not found")
    campaign = await db.get(Campaign, creative.campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="creative not found")
    biz = await get_business_for_user(db, user_id, campaign.business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="creative not found")
    return creative, campaign


@router.post(
    "/creatives/{creative_id}/schedule",
    response_model=list[ScheduledPostResponse],
    status_code=201,
)
async def schedule_creative(
    creative_id: uuid.UUID,
    body: ScheduleRequest,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[ScheduledPostResponse]:
    user_row = await sync_user_from_supabase(db, user)
    _, campaign = await _creative_for_user(db, user_row.id, creative_id)

    created: list[ScheduledPost] = []
    for target in body.targets:
        try:
            row = await post_scheduler.schedule_post(
                db,
                master_creative_id=creative_id,
                business_id=campaign.business_id,
                platform=target.platform,
                aspect=target.aspect,
                scheduled_at=body.scheduled_at,
                caption=target.caption,
                require_approval=body.require_approval,
            )
        except post_scheduler.ScheduleValidationError as e:
            raise ClientError(
                "schedule_invalid",
                status_code=422,
                message=str(e),
            ) from e
        created.append(row)
    await db.commit()
    for r in created:
        await db.refresh(r)
    return [
        ScheduledPostResponse.model_validate(r, from_attributes=True) for r in created
    ]


@router.get(
    "/creatives/{creative_id}/schedule",
    response_model=list[ScheduledPostResponse],
)
async def list_creative_schedule(
    creative_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[ScheduledPostResponse]:
    user_row = await sync_user_from_supabase(db, user)
    await _creative_for_user(db, user_row.id, creative_id)
    q = await db.execute(
        select(ScheduledPost)
        .where(ScheduledPost.master_creative_id == creative_id)
        .order_by(ScheduledPost.scheduled_at.asc())
    )
    return [
        ScheduledPostResponse.model_validate(r, from_attributes=True)
        for r in q.scalars().all()
    ]


@router.get(
    "/businesses/{business_id}/schedule",
    response_model=list[ScheduledPostResponse],
)
async def list_business_schedule(
    business_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[ScheduledPostResponse]:
    user_row = await sync_user_from_supabase(db, user)
    biz = await get_business_for_user(db, user_row.id, business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="business not found")
    q = await db.execute(
        select(ScheduledPost)
        .where(ScheduledPost.business_id == business_id)
        .order_by(ScheduledPost.scheduled_at.asc())
    )
    return [
        ScheduledPostResponse.model_validate(r, from_attributes=True)
        for r in q.scalars().all()
    ]


@router.post(
    "/scheduled_posts/{post_id}/cancel",
    response_model=ScheduledPostResponse,
)
async def cancel_scheduled_post(
    post_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> ScheduledPostResponse:
    user_row = await sync_user_from_supabase(db, user)
    row = await db.get(ScheduledPost, post_id)
    if row is None:
        raise HTTPException(status_code=404, detail="post not found")
    biz = await get_business_for_user(db, user_row.id, row.business_id)
    if biz is None:
        raise HTTPException(status_code=404, detail="post not found")

    try:
        updated = await post_scheduler.cancel_post(db, scheduled_post_id=post_id)
    except post_scheduler.ScheduleValidationError as e:
        raise ClientError(
            "schedule_conflict",
            status_code=409,
            message=str(e),
        ) from e
    await db.commit()
    await db.refresh(updated)
    return ScheduledPostResponse.model_validate(updated, from_attributes=True)

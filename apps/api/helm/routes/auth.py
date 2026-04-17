"""Auth endpoints.

POST /auth/sync is called by the client once, immediately after a successful Supabase
signin, to upsert the user record in our DB. We derive identity from the JWT, not the
request body — the client cannot forge a different user ID.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.session import get_session
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(prefix="/auth", tags=["auth"])


class SyncedUser(BaseModel):
    user_id: str
    email: str
    tier: str
    kill_switch_active: bool


@router.post("/sync", response_model=SyncedUser)
async def sync_user(
    user: CurrentUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> SyncedUser:
    record = await sync_user_from_supabase(session, user)
    return SyncedUser(
        user_id=str(record.id),
        email=record.email,
        tier=record.tier,
        kill_switch_active=record.kill_switch_active,
    )

"""Auth endpoints.

POST /auth/sync is called by the client once, immediately after a successful Supabase
signin, to upsert the user record in our DB. We derive identity from the JWT, not the
request body — the client cannot forge a different user ID.

POST /auth/push_token registers an Expo push token so approvals-ready pushes can
land on the user's phone while the app is backgrounded.
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


class PushTokenRequest(BaseModel):
    token: str | None


@router.post("/push_token")
async def register_push_token(
    body: PushTokenRequest,
    user: CurrentUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Upsert the user's Expo push token.

    Passing null (or omitting the token) clears it — clients that revoke
    notification permission or sign out should clear so we stop sending.
    """
    record = await sync_user_from_supabase(session, user)
    record.expo_push_token = body.token or None
    await session.commit()
    return {"status": "ok"}

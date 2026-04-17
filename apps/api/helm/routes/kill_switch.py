"""POST /users/me/kill_switch — flip the user-level PAUSE_ALL_AGENTS flag.

CLAUDE.md hard rule #2: this must halt every running agent within 2 seconds.
The runtime checks `kill_switch.is_active` before every tool call; our cache
TTL is 1s, so the worst-case response time to a toggle is ~1s.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser, require_user
from helm.db.session import get_session
from helm.services import kill_switch
from helm.services.user_sync import sync_user_from_supabase

router = APIRouter(prefix="/users/me", tags=["safety"])


class KillSwitchState(BaseModel):
    active: bool


@router.get("/kill_switch", response_model=KillSwitchState)
async def get_state(
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> KillSwitchState:
    record = await sync_user_from_supabase(db, user)
    return KillSwitchState(active=await kill_switch.is_active(db, record.id))


@router.post("/kill_switch", response_model=KillSwitchState)
async def set_state(
    body: KillSwitchState,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> KillSwitchState:
    record = await sync_user_from_supabase(db, user)
    await kill_switch.toggle(db, record.id, body.active)
    return body

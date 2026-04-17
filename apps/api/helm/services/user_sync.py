"""Upsert the local `users` row from a verified Supabase JWT.

We keep a local row because every tenant-scoped table uses `users.id` (a UUID we
generate) as the foreign key — we don't want to rely on the Supabase `sub` being
addressable everywhere in our schema. On first call we insert; on subsequent calls
we refresh the email if it changed (users can update it in Supabase).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.auth import CurrentUser
from helm.db.models import User


async def sync_user_from_supabase(session: AsyncSession, authed: CurrentUser) -> User:
    result = await session.execute(select(User).where(User.supabase_id == authed.supabase_id))
    existing = result.scalar_one_or_none()

    if existing is not None:
        if existing.email != authed.email:
            existing.email = authed.email
            await session.commit()
            await session.refresh(existing)
        return existing

    user = User(supabase_id=authed.supabase_id, email=authed.email, tier="founder")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user

"""Tenant-scoped query helpers.

The one rule: every business read or write goes through one of these helpers, which
assert ownership before returning. Bypassing them is a security bug.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helm.db.models import Business


async def list_businesses_for_user(session: AsyncSession, user_id: uuid.UUID) -> Sequence[Business]:
    """Return only the businesses owned by `user_id`."""
    result = await session.execute(
        select(Business).where(Business.user_id == user_id).order_by(Business.created_at)
    )
    return result.scalars().all()


async def get_business_for_user(
    session: AsyncSession, user_id: uuid.UUID, business_id: uuid.UUID
) -> Business | None:
    """Fetch a business only if `user_id` owns it. Returns None otherwise (caller
    raises 404 — we deliberately do not leak "exists but not yours" vs "doesn't exist")."""
    result = await session.execute(
        select(Business).where(Business.id == business_id, Business.user_id == user_id)
    )
    return result.scalar_one_or_none()

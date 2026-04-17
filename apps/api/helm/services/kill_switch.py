"""Global kill switch — halts every agent call for a user.

CLAUDE.md hard rule #2: `PAUSE_ALL_AGENTS` at the user level must stop every
running agent in <2 seconds. Every tool wrapper must check before executing
(see `helm.agents.runtime._execute_tool`).

Implementation: a boolean column on `users` plus an in-process 1-second TTL
cache per worker. That buys us sub-ms checks on the hot path without the
need for Redis in Phase 1. If the check is stale, the worst-case window is
1s — still under the 2s SLA. Redis mirror can be added when we scale out.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from helm.db.models import User


class KillSwitchActivated(Exception):  # noqa: N818 — reads naturally in tool wrappers
    """Raised when a tool wrapper detects the kill switch is on for this user."""

    def __init__(self, user_id: uuid.UUID):
        super().__init__(f"kill switch activated for user {user_id}")
        self.user_id = user_id


@dataclass(slots=True)
class _CacheEntry:
    active: bool
    fetched_at: float


_cache: dict[uuid.UUID, _CacheEntry] = {}
_cache_lock = asyncio.Lock()
_TTL_SECONDS = 1.0


async def is_active(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """Read-through cache: a hit inside the TTL is sub-ms; a miss is one
    Postgres row read. Mutations (`toggle`) invalidate immediately."""
    now = time.monotonic()
    entry = _cache.get(user_id)
    if entry is not None and (now - entry.fetched_at) < _TTL_SECONDS:
        return entry.active

    async with _cache_lock:
        entry = _cache.get(user_id)
        if entry is not None and (time.monotonic() - entry.fetched_at) < _TTL_SECONDS:
            return entry.active
        result = await session.execute(select(User.kill_switch_active).where(User.id == user_id))
        active = bool(result.scalar_one())
        _cache[user_id] = _CacheEntry(active=active, fetched_at=time.monotonic())
        return active


async def assert_not_set(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Raise `KillSwitchActivated` if the switch is on. Call before every tool."""
    if await is_active(session, user_id):
        raise KillSwitchActivated(user_id)


async def toggle(session: AsyncSession, user_id: uuid.UUID, active: bool) -> bool:
    """Set the kill switch state. Returns the new value. Commits + invalidates
    the cache synchronously so the next `is_active` call sees the truth."""
    await session.execute(update(User).where(User.id == user_id).values(kill_switch_active=active))
    await session.commit()
    _cache[user_id] = _CacheEntry(active=active, fetched_at=time.monotonic())
    return active


def _invalidate_cache_for_tests() -> None:
    """Tests that toggle user state by mutating rows directly (not via
    `toggle()`) must clear the cache to see their writes."""
    _cache.clear()

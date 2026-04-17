"""Kill switch service — cache correctness + toggle path.

The SLA is "every running agent stops in <2 seconds" (CLAUDE.md hard rule #2).
Our implementation is: per-process 1s-TTL cache + Postgres column. A fresh
`toggle()` invalidates the cache immediately so the next read is authoritative.
"""

from __future__ import annotations

import time

import pytest
from helm.db.models import User
from helm.services import kill_switch

from tests.conftest import requires_db


@requires_db
@pytest.mark.asyncio
async def test_toggle_takes_effect_on_next_check(session) -> None:
    user = User(supabase_id="sub-k1", email="k1@example.com", tier="founder")
    session.add(user)
    await session.commit()

    # Clear any stale cache from a prior test in this process.
    kill_switch._invalidate_cache_for_tests()

    assert await kill_switch.is_active(session, user.id) is False

    await kill_switch.toggle(session, user.id, True)
    assert await kill_switch.is_active(session, user.id) is True

    with pytest.raises(kill_switch.KillSwitchActivated) as exc:
        await kill_switch.assert_not_set(session, user.id)
    assert exc.value.user_id == user.id

    await kill_switch.toggle(session, user.id, False)
    assert await kill_switch.is_active(session, user.id) is False
    await kill_switch.assert_not_set(session, user.id)  # no raise


@requires_db
@pytest.mark.asyncio
async def test_cache_hit_avoids_repeat_db_reads(session) -> None:
    """After one read, subsequent reads within the TTL hit the cache.
    We verify by deleting the user row and confirming the stale cache is still
    used — then waiting past the TTL and confirming it re-reads (and fails).
    """
    user = User(supabase_id="sub-k2", email="k2@example.com", tier="founder")
    session.add(user)
    await session.commit()
    user_id = user.id

    kill_switch._invalidate_cache_for_tests()
    assert await kill_switch.is_active(session, user_id) is False  # cached

    await session.delete(user)
    await session.commit()

    # Stale cache still serves the old value.
    assert await kill_switch.is_active(session, user_id) is False

    # Force-expire the cache by rewinding the fetched_at time.
    entry = kill_switch._cache[user_id]
    kill_switch._cache[user_id] = kill_switch._CacheEntry(
        active=entry.active, fetched_at=time.monotonic() - 10
    )
    # Next read re-queries Postgres — row is gone, raises.
    from sqlalchemy.exc import NoResultFound

    with pytest.raises(NoResultFound):
        await kill_switch.is_active(session, user_id)

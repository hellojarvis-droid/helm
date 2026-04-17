"""Tenant isolation baseline.

CLAUDE.md hard rule #1: multi-tenant from line 1. This test fails closed — user A
must not be able to read user B's business through any tenant helper.

We exercise `get_business_for_user` (the scoped accessor) and `list_businesses_for_user`
(the scoped list). Direct SQLAlchemy queries are explicitly not the tenant surface —
those must only be used inside tenant helpers that prove ownership.
"""

from __future__ import annotations

import pytest
from helm.db.models import Business, User
from helm.db.tenant import get_business_for_user, list_businesses_for_user

from tests.conftest import requires_db


@requires_db
@pytest.mark.asyncio
async def test_user_cannot_read_another_users_business(session) -> None:
    user_a = User(supabase_id="sub-a", email="a@example.com", tier="founder")
    user_b = User(supabase_id="sub-b", email="b@example.com", tier="founder")
    session.add_all([user_a, user_b])
    await session.flush()

    biz_a = Business(user_id=user_a.id, name="A's candle store", vertical="dtc_physical")
    biz_b = Business(user_id=user_b.id, name="B's dog bandanas", vertical="dtc_physical")
    session.add_all([biz_a, biz_b])
    await session.commit()

    # user_a asking for user_a's business — OK
    got = await get_business_for_user(session, user_a.id, biz_a.id)
    assert got is not None
    assert got.id == biz_a.id

    # user_a asking for user_b's business — MUST fail closed
    leaked = await get_business_for_user(session, user_a.id, biz_b.id)
    assert leaked is None, "cross-tenant read leaked a business"

    # list isolation
    a_list = await list_businesses_for_user(session, user_a.id)
    assert [b.id for b in a_list] == [biz_a.id]

    b_list = await list_businesses_for_user(session, user_b.id)
    assert [b.id for b in b_list] == [biz_b.id]


@requires_db
@pytest.mark.asyncio
async def test_user_sync_is_idempotent(session) -> None:
    from helm.auth import CurrentUser
    from helm.services.user_sync import sync_user_from_supabase

    authed = CurrentUser(supabase_id="sub-x", email="x@example.com", raw_claims={})
    first = await sync_user_from_supabase(session, authed)
    second = await sync_user_from_supabase(session, authed)
    assert first.id == second.id

    # Email update propagates on re-sync
    authed2 = CurrentUser(supabase_id="sub-x", email="x2@example.com", raw_claims={})
    third = await sync_user_from_supabase(session, authed2)
    assert third.id == first.id
    assert third.email == "x2@example.com"

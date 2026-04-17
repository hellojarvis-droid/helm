"""Test fixtures.

DB tests need a real Postgres with pgvector. In CI that's the `pgvector/pg16` service.
Locally it's any Postgres 16 with pgvector enabled — point `TEST_DATABASE_URL` at it
and run `alembic upgrade head` first. Tests that need the DB skip cleanly when the
env var is absent, so the default `pytest` stays useful on a fresh laptop.

Why per-test engine (NullPool) instead of a session-scoped one:
asyncpg connections are bound to the asyncio event loop they were opened on.
pytest-asyncio creates a fresh loop per async test, so a pooled connection created
in the session-scoped fixture can't be reused in a later test — asyncpg raises
"Future attached to a different loop". Opening a disposable engine per test avoids
this entirely. The Postgres side stays fast: we only `TRUNCATE`, never `DROP`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import NullPool, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _test_db_url() -> str | None:
    return os.getenv("TEST_DATABASE_URL")


requires_db = pytest.mark.skipif(
    _test_db_url() is None,
    reason="TEST_DATABASE_URL not set",
)


_TRUNCATE_SQL = (
    "TRUNCATE users, businesses, agent_sessions, agent_events, "
    "approvals, agent_memories, integrations RESTART IDENTITY CASCADE"
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    url = _test_db_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL not set")

    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(_TRUNCATE_SQL))

        sm = async_sessionmaker(engine, expire_on_commit=False)
        async with sm() as s:
            yield s
    finally:
        await engine.dispose()

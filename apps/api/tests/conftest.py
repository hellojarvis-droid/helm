"""Test fixtures.

Tests that need the DB use a real Postgres (pgvector/pg16 in CI; a local Postgres or
Supabase dev branch locally). The URL comes from TEST_DATABASE_URL; tests that need
the DB are skipped when it's absent, so `pytest` stays useful even without a DB
running.

Strategy:
- One session-scoped fixture creates the schema from SQLAlchemy metadata (no Alembic
  — we want a clean drop/create per session for test isolation).
- Per-test, we truncate rather than drop/recreate — 50x faster.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from helm.db.models import Base
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
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


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    url = _test_db_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL not set")
    eng = create_async_engine(url, pool_pre_ping=True)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Truncate all tables before each test; yield a session bound to a new connection."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE users, businesses, agent_sessions, agent_events, "
                "approvals, agent_memories, integrations RESTART IDENTITY CASCADE"
            )
        )
    async with sm() as s:
        yield s

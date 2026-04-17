"""Async SQLAlchemy engine + session factory.

Engine is lazy so `import helm.main` works in environments without DATABASE_URL
(tests, CI, bare /health). Use `get_session` as a FastAPI dependency; use
`session_scope()` for scripts.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from helm.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = get_settings().database_url
        if not url:
            raise RuntimeError("DATABASE_URL is not configured")
        _engine = create_async_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with get_sessionmaker()() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """For scripts and background tasks."""
    async with get_sessionmaker()() as session:
        yield session


def reset_engine_for_tests() -> None:
    """Used by the test suite to force re-initialization against a different URL."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None

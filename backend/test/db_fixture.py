"""Shared in-memory database wiring for repository suites.

Import this only after DATABASE_URL is set: the SQLAlchemy base module refuses to
load without it.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from sqlalchemy import Table
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from infr.config.base import Base


@compiles(MEDIUMTEXT, "sqlite")
def _compile_mediumtext_for_sqlite(_type: MEDIUMTEXT, _compiler, **_kwargs) -> str:
    return "TEXT"


@asynccontextmanager
async def sqlite_session(tables: Sequence[Table]) -> AsyncIterator[AsyncSession]:
    """Yield a session backed by a throwaway SQLite database holding `tables`."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=list(tables),
                )
            )

        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            yield session
            await session.rollback()
    finally:
        await engine.dispose()

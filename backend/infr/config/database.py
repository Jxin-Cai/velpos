from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.exc import OperationalError, PendingRollbackError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from infr.config.base import DATABASE_URL

logger = logging.getLogger(__name__)

_is_sqlite = DATABASE_URL.startswith("sqlite")

if not _is_sqlite:
    from sqlalchemy.dialects.mysql import aiomysql as _sa_aiomysql

    # SQLAlchemy 2.0.49 + aiomysql 0.3.2: ping(reconnect) lacks a default value,
    # causing TypeError when pool_pre_ping calls ping() without arguments.
    _orig_aiomysql_ping = _sa_aiomysql.AsyncAdapt_aiomysql_connection.ping

    def _patched_aiomysql_ping(self, reconnect: bool = False) -> None:
        return _orig_aiomysql_ping(self, reconnect)

    _sa_aiomysql.AsyncAdapt_aiomysql_connection.ping = _patched_aiomysql_ping

__all__ = ["DATABASE_URL", "async_engine", "async_session_factory", "get_async_session", "is_sqlite"]

is_sqlite: bool = _is_sqlite

_engine_kwargs: dict = {
    "echo": False,
    "pool_pre_ping": True,
}
if not _is_sqlite:
    _engine_kwargs.update(
        pool_recycle=1800,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
    )

async_engine = create_async_engine(DATABASE_URL, **_engine_kwargs)

async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except PendingRollbackError:
            logger.warning("DB session in invalid transaction state, rolling back")
            await session.rollback()
        except OperationalError:
            logger.error("DB commit failed (connection lost)", exc_info=True)
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            raise

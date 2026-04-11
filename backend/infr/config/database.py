from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.exc import OperationalError, PendingRollbackError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from infr.config.base import DATABASE_URL, Base

logger = logging.getLogger(__name__)

__all__ = ["DATABASE_URL", "Base", "async_engine", "async_session_factory", "get_async_session"]

async_engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
)

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
        except OperationalError as e:
            logger.error("DB commit failed (connection lost): %s", e)
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            raise

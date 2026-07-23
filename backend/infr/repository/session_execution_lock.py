from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text

from domain.shared.business_exception import BusinessException
from infr.config.database import async_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def acquire_session_execution_lock(
    session_id: str,
    timeout_seconds: int = 30,
) -> AsyncIterator[None]:
    """Serialize a session across all MySQL-backed application instances."""
    async with async_engine.connect() as connection:
        if connection.dialect.name != "mysql":
            yield
            return

        lock_name = f"velpos:session-execution:{session_id}"
        acquired = await connection.scalar(
            text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
            {"lock_name": lock_name, "timeout_seconds": timeout_seconds},
        )
        if acquired != 1:
            raise BusinessException(
                "Session is being processed by another worker",
                "SESSION_EXECUTION_BUSY",
            )
        try:
            yield
        finally:
            try:
                await connection.execute(
                    text("SELECT RELEASE_LOCK(:lock_name)"),
                    {"lock_name": lock_name},
                )
            except Exception:
                logger.error(
                    "Failed to release distributed session lock: session_id=%s",
                    session_id,
                    exc_info=True,
                )

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def safe_create_task(coro, *, name: str | None = None) -> asyncio.Task:
    """Create an asyncio task with automatic exception logging.

    Fire-and-forget tasks created with plain ``asyncio.create_task`` silently
    swallow exceptions (Python only emits "Task exception was never retrieved"
    on GC).  This wrapper attaches a done-callback that logs any unhandled
    exception at ERROR level.
    """
    task = asyncio.create_task(coro, name=name)

    def _log_exception(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error(
                "Unhandled exception in background task %s: %s",
                t.get_name(),
                exc,
                exc_info=exc,
            )

    task.add_done_callback(_log_exception)
    return task

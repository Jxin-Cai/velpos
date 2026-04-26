from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from application.scheduler.scheduler_application_service import SchedulerApplicationService
from infr.config.database import async_session_factory
from infr.repository.project_repository_impl import ProjectRepositoryImpl
from infr.repository.scheduled_task_repository_impl import ScheduledTaskRepositoryImpl
from ohs.dependencies import (
    _save_scheduled_task_run,
    _im_bind_for_session,
    _im_unbind_for_session,
    _on_assistant_response,
    get_connection_manager,
    get_create_session_service_factory,
)

logger = logging.getLogger(__name__)


class SchedulerRunner:

    def __init__(self, interval_seconds: int = 30) -> None:
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopped.clear()
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        while not self._stopped.is_set():
            try:
                await self._run_once()
            except Exception:
                logger.warning("scheduler runner tick failed", exc_info=True)
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def _run_once(self) -> None:
        async with async_session_factory() as db_session:
            service = SchedulerApplicationService(
                repository=ScheduledTaskRepositoryImpl(db_session),
                project_repository=ProjectRepositoryImpl(db_session),
                session_service_factory=get_create_session_service_factory(),
                connection_manager=get_connection_manager(),
                notify_im_fn=_on_assistant_response,
                bind_im_fn=_im_bind_for_session,
                unbind_im_fn=_im_unbind_for_session,
                save_run_fn=_save_scheduled_task_run,
            )
            runs = await service.run_due_tasks()
            await db_session.commit()
            if runs:
                logger.info("scheduler triggered %d task(s)", len(runs))

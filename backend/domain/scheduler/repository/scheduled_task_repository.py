from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from domain.scheduler.model.scheduled_task import ScheduledTask, ScheduledTaskRun


class ScheduledTaskRepository(ABC):

    @abstractmethod
    async def save(self, task: ScheduledTask) -> None:
        ...

    @abstractmethod
    async def save_run(self, run: ScheduledTaskRun) -> None:
        ...

    @abstractmethod
    async def find_by_id(self, task_id: str) -> ScheduledTask | None:
        ...

    @abstractmethod
    async def find_all(self) -> list[ScheduledTask]:
        ...

    @abstractmethod
    async def find_due(self, now: datetime) -> list[ScheduledTask]:
        ...

    @abstractmethod
    async def find_runs_by_task_id(self, task_id: str) -> list[ScheduledTaskRun]:
        ...

    @abstractmethod
    async def remove(self, task_id: str) -> bool:
        ...

    @abstractmethod
    async def commit(self) -> None:
        ...

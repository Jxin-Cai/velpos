from __future__ import annotations

from abc import ABC, abstractmethod

from domain.team_task.model.team_task import TeamTask


class TeamTaskRepository(ABC):

    @abstractmethod
    async def save(self, task: TeamTask) -> None: ...

    @abstractmethod
    async def find_by_id(self, task_id: str) -> TeamTask | None: ...

    @abstractmethod
    async def find_by_coordinator(self, coordinator_session_id: str) -> list[TeamTask]: ...

    @abstractmethod
    async def find_running_by_coordinator(self, coordinator_session_id: str) -> list[TeamTask]: ...

    @abstractmethod
    async def remove(self, task_id: str) -> bool: ...

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.memory.model.project_memory_entry import ProjectMemoryEntry


class ProjectMemoryRepository(ABC):

    @abstractmethod
    async def save(self, entry: ProjectMemoryEntry) -> None:
        ...

    @abstractmethod
    async def find_by_id(self, memory_id: str) -> ProjectMemoryEntry | None:
        ...

    @abstractmethod
    async def find_by_project_id(self, project_id: str) -> list[ProjectMemoryEntry]:
        ...

    @abstractmethod
    async def remove(self, memory_id: str) -> bool:
        ...

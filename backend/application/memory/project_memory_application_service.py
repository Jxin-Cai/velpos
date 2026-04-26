from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from domain.memory.model.project_memory_entry import ProjectMemoryEntry
from domain.memory.repository.project_memory_repository import ProjectMemoryRepository
from domain.project.model.project import Project
from domain.project.repository.project_repository import ProjectRepository
from domain.shared.business_exception import BusinessException


@dataclass(frozen=True)
class ProjectMemoryTarget:
    project_id: str = ""
    project_dir: str = ""


class ProjectMemoryApplicationService:

    def __init__(
        self,
        memory_repository: ProjectMemoryRepository,
        project_repository: ProjectRepository,
    ) -> None:
        self._memory_repository = memory_repository
        self._project_repository = project_repository

    async def list_memories(self, project_id: str = "", project_dir: str = "") -> list[ProjectMemoryEntry]:
        project = await self._resolve_project(project_id, project_dir)
        return await self._memory_repository.find_by_project_id(project.id)

    async def create_memory(
        self,
        project_id: str = "",
        project_dir: str = "",
        memory_type: str = "note",
        title: str = "",
        content: str = "",
        source_session_id: str = "",
        source_message_id: str = "",
        visibility: str = "project",
    ) -> ProjectMemoryEntry:
        project = await self._resolve_project(project_id, project_dir)
        if not title.strip():
            raise BusinessException("Memory title is required")
        entry = ProjectMemoryEntry.create(
            project_id=project.id,
            memory_type=memory_type,
            title=title,
            content=content,
            source_session_id=source_session_id,
            source_message_id=source_message_id,
            visibility=visibility,
        )
        await self._memory_repository.save(entry)
        return entry

    async def update_memory(
        self,
        memory_id: str,
        title: str | None = None,
        content: str | None = None,
        memory_type: str | None = None,
        visibility: str | None = None,
        state: str | None = None,
    ) -> ProjectMemoryEntry:
        entry = await self._get_memory(memory_id)
        entry.update(
            title=title,
            content=content,
            memory_type=memory_type,
            visibility=visibility,
            state=state,
        )
        await self._memory_repository.save(entry)
        return entry

    async def delete_memory(self, memory_id: str) -> None:
        removed = await self._memory_repository.remove(memory_id)
        if not removed:
            raise BusinessException("Project memory not found")

    async def _get_memory(self, memory_id: str) -> ProjectMemoryEntry:
        entry = await self._memory_repository.find_by_id(memory_id)
        if entry is None:
            raise BusinessException("Project memory not found")
        return entry

    async def _resolve_project(self, project_id: str = "", project_dir: str = "") -> Project:
        if project_id:
            project = await self._project_repository.find_by_id(project_id)
            if project is None:
                raise BusinessException("Project not found")
            return project
        if not project_dir:
            raise BusinessException("Project id or directory is required")
        project_path = Path(project_dir).expanduser().resolve()
        if not project_path.is_dir():
            raise BusinessException("Project directory not found")
        project = await self._project_repository.find_by_dir_path(str(project_path))
        if project is None:
            project = Project.create(project_path.name, str(project_path))
            await self._project_repository.save(project)
        return project

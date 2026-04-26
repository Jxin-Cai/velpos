from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.memory.model.project_memory_entry import ProjectMemoryEntry
from domain.memory.repository.project_memory_repository import ProjectMemoryRepository
from infr.repository.project_memory_entry_model import ProjectMemoryEntryModel


class ProjectMemoryRepositoryImpl(ProjectMemoryRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, entry: ProjectMemoryEntry) -> None:
        await self._session.merge(self._to_model(entry))
        await self._session.flush()

    async def find_by_id(self, memory_id: str) -> ProjectMemoryEntry | None:
        stmt = select(ProjectMemoryEntryModel).where(ProjectMemoryEntryModel.id == memory_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_project_id(self, project_id: str) -> list[ProjectMemoryEntry]:
        stmt = (
            select(ProjectMemoryEntryModel)
            .where(ProjectMemoryEntryModel.project_id == project_id)
            .order_by(ProjectMemoryEntryModel.updated_time.desc(), ProjectMemoryEntryModel.created_time.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def remove(self, memory_id: str) -> bool:
        stmt = select(ProjectMemoryEntryModel).where(ProjectMemoryEntryModel.id == memory_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    @staticmethod
    def _to_model(entry: ProjectMemoryEntry) -> ProjectMemoryEntryModel:
        return ProjectMemoryEntryModel(
            id=entry.id,
            project_id=entry.project_id,
            memory_type=entry.memory_type,
            title=entry.title,
            content=entry.content,
            source_session_id=entry.source_session_id,
            source_message_id=entry.source_message_id,
            visibility=entry.visibility,
            state=entry.state,
            created_time=entry.created_time,
            updated_time=entry.updated_time,
        )

    @staticmethod
    def _to_domain(model: ProjectMemoryEntryModel) -> ProjectMemoryEntry:
        return ProjectMemoryEntry(
            id=model.id,
            project_id=model.project_id,
            memory_type=model.memory_type,
            title=model.title,
            content=model.content,
            source_session_id=model.source_session_id,
            source_message_id=model.source_message_id,
            visibility=model.visibility,
            state=model.state,
            created_time=model.created_time,
            updated_time=model.updated_time,
        )

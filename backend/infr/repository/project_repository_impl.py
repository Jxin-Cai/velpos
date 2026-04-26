from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.project.model.project import Project
from domain.project.repository.project_repository import ProjectRepository
from infr.repository.project_model import ProjectModel


class ProjectRepositoryImpl(ProjectRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, project: Project) -> None:
        model = self._to_model(project)
        await self._session.merge(model)
        await self._session.flush()

    async def find_by_id(self, project_id: str) -> Project | None:
        stmt = select(ProjectModel).where(ProjectModel.id == project_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_all(self) -> list[Project]:
        stmt = select(ProjectModel).order_by(
            ProjectModel.sort_order.desc(),
            ProjectModel.created_time.desc(),
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def find_by_dir_path(self, dir_path: str) -> Project | None:
        stmt = select(ProjectModel).where(ProjectModel.dir_path == dir_path).limit(1)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def remove(self, project_id: str) -> bool:
        stmt = select(ProjectModel).where(ProjectModel.id == project_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    @staticmethod
    def _to_model(project: Project) -> ProjectModel:
        return ProjectModel(
            id=project.id,
            name=project.name,
            dir_path=project.dir_path,
            agents_json=project.agents,
            plugins_json=project.plugins,
            sort_order=project.sort_order,
            active_claude_md_revision_id=project.active_claude_md_revision_id,
            claude_md_file_hash=project.claude_md_file_hash,
            created_time=project.created_at,
            updated_time=project.updated_at,
        )

    @staticmethod
    def _to_domain(model: ProjectModel) -> Project:
        return Project.reconstitute(
            id=model.id,
            name=model.name,
            dir_path=model.dir_path,
            agents=model.agents_json or {},
            plugins=model.plugins_json or {},
            sort_order=model.sort_order,
            active_claude_md_revision_id=model.active_claude_md_revision_id,
            claude_md_file_hash=model.claude_md_file_hash,
            created_at=model.created_time,
            updated_at=model.updated_time,
        )

from __future__ import annotations

from pathlib import Path

from domain.project.model.project import Project
from domain.project.repository.project_repository import ProjectRepository
from domain.shared.business_exception import BusinessException


async def resolve_project(
    project_repository: ProjectRepository,
    project_id: str = "",
    project_dir: str = "",
) -> Project:
    if project_id:
        project = await project_repository.find_by_id(project_id)
        if project is None:
            raise BusinessException("Project not found")
        return project
    if not project_dir:
        raise BusinessException("Project id or directory is required")
    project_path = Path(project_dir).expanduser().resolve()
    if not project_path.is_dir():
        raise BusinessException("Project directory not found")
    project = await project_repository.find_by_dir_path(str(project_path))
    if project is None:
        project = Project.create(project_path.name, str(project_path))
        await project_repository.save(project)
    return project

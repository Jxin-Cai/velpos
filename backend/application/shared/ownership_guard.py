from __future__ import annotations

from domain.project.repository.project_repository import ProjectRepository
from domain.shared.business_exception import BusinessException
from infr.config.app_config import app_config


async def ensure_user_owns_project(
    project_repo: ProjectRepository,
    project_id: str,
    user_id: int,
) -> None:
    if app_config.mode == "dev":
        return
    project = await project_repo.find_by_id(project_id)
    if project is None or project.user_id != user_id:
        raise BusinessException("Project not found", "PROJECT_NOT_FOUND")


async def ensure_user_owns_session(
    project_repo: ProjectRepository,
    session_project_id: str,
    user_id: int,
) -> None:
    if app_config.mode == "dev":
        return
    if not session_project_id:
        return
    project = await project_repo.find_by_id(session_project_id)
    if project is None or project.user_id != user_id:
        raise BusinessException("Session not found", "SESSION_NOT_FOUND")

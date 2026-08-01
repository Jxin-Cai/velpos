from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from domain.project.model.project import Project
from domain.team.acl.workspace_gateway import WorkspaceUnavailableError
from domain.team.model.team_domain_error import TeamDomainError

if TYPE_CHECKING:
    from domain.project.repository.project_repository import ProjectRepository
    from domain.team.acl.workspace_gateway import WorkspaceGateway
    from domain.team.model.agent_slot import AgentSlot
    from domain.team.model.team import Team
    from domain.team.repository.team_repository import TeamRepository

logger = logging.getLogger(__name__)


async def ensure_agent_project(
    team_name: str,
    slot: AgentSlot,
    project_repo: ProjectRepository,
    user_id: int | None = None,
    team_project_id: str = "",
) -> Project:
    project_name = f"{team_name}-{slot.name}"
    project = await project_repo.find_by_dir_path(slot.workspace_ref)
    if project is None:
        if user_id is None and team_project_id:
            team_project = await project_repo.find_by_id(team_project_id)
            user_id = team_project.user_id if team_project is not None else None
        if user_id is None:
            raise TeamDomainError("Cannot resolve the owner of the agent workspace")
        project = Project.create(
            name=project_name,
            dir_path=slot.workspace_ref,
            user_id=user_id,
        )
    elif project.project_type == "team":
        raise TeamDomainError(
            f"Agent workspace is already owned by a team project: {slot.workspace_ref}"
        )

    changed = False
    if project.name != project_name:
        project.rename(project_name)
        changed = True
    current_agent = project.get_current_agent()
    if not current_agent or current_agent.get("id") != slot.role:
        project.load_agent(slot.role, "zh")
        changed = True
    if changed:
        await project_repo.save(project)
    return project


async def prepare_execution_workspace(
    team: Team,
    target_slot: AgentSlot,
    execution_id: str,
    workspace_gateway: WorkspaceGateway,
    team_repo: TeamRepository,
) -> str:
    try:
        return workspace_gateway.create_execution_workspace(
            target_slot.workspace_ref,
            execution_id,
        )
    except WorkspaceUnavailableError as error:
        target_slot.mark_unstable()
        await team_repo.save(team)
        logger.warning(
            "agent workspace unavailable for team %s slot %s",
            team.id,
            target_slot.id,
        )
        raise TeamDomainError(
            "Target agent workspace is unavailable; restore its workspace "
            "directory or recreate the team"
        ) from error

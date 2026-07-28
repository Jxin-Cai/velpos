from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from application.team_board.team_workspace_helpers import ensure_agent_project
from domain.team.model.team_domain_error import TeamDomainError

if TYPE_CHECKING:
    from application.team_board.commands import CreateTeamCommand
    from domain.project.acl.plugin_manager import PluginManager
    from domain.project.repository.project_repository import ProjectRepository
    from domain.team.acl.workspace_gateway import WorkspaceGateway
    from domain.team.model.team import Team
    from domain.team.repository.team_repository import TeamRepository

logger = logging.getLogger(__name__)


class TeamLifecycleService:
    def __init__(
        self,
        team_repo: TeamRepository,
        workspace_gateway: WorkspaceGateway,
        project_repo: ProjectRepository,
        plugin_manager: PluginManager | None = None,
        agent_catalog_fn=None,
    ) -> None:
        self._team_repo = team_repo
        self._workspace = workspace_gateway
        self._project_repo = project_repo
        self._plugin_manager = plugin_manager
        self._agent_catalog_fn = agent_catalog_fn

    async def create_team(self, cmd: CreateTeamCommand) -> Team:
        from domain.team.model.team import Team

        team = Team.create(project_id=cmd.project_id, name=cmd.name)
        workspace_refs: list[str] = []
        try:
            for index, slot_cfg in enumerate(cmd.slots, start=1):
                workspace_ref = self._workspace.create_independent_workspace(
                    team_root=cmd.root_path,
                    team_slug=cmd.name,
                    slot_slug=slot_cfg.slug or slot_cfg.display_name or f"agent-{index}",
                    project_root=cmd.root_path,
                    agent_profile_ref=slot_cfg.agent_profile_id,
                )
                workspace_refs.append(workspace_ref)
                await self._load_agent_profile(slot_cfg.agent_profile_id, workspace_ref)
                slot = team.add_agent_slot(
                    name=slot_cfg.display_name,
                    role=slot_cfg.agent_profile_id,
                    workspace_ref=workspace_ref,
                )
                await ensure_agent_project(team.name, slot, self._project_repo)
            await self._team_repo.save(team)
        except Exception:
            logger.exception("workspace preparation failed for team %s", team.id)
            for workspace_ref in reversed(workspace_refs):
                self._workspace.remove_workspace(workspace_ref)
            raise
        return team

    async def list_teams(self, project_id: str) -> list[Team]:
        team = await self._team_repo.find_by_project_id(project_id)
        return [team] if team is not None else []

    async def _load_agent_profile(self, agent_profile_id: str, workspace_ref: str) -> None:
        if self._plugin_manager is None:
            return

        profile: dict | None = None
        if self._agent_catalog_fn is not None:
            profile = self._agent_catalog_fn(agent_profile_id)
        if profile is None:
            return

        marketplace_config = profile.get("marketplace_plugins", {})
        for marketplace in marketplace_config.get("marketplaces", []):
            name = marketplace.get("name", "")
            source = marketplace.get("source", "")
            if not name or not source:
                continue
            try:
                if not self._plugin_manager.is_marketplace_added(name):
                    await self._plugin_manager.add_marketplace(source)
                else:
                    await self._plugin_manager.update_marketplace(name)
            except Exception:
                logger.warning(
                    "failed to prepare agent marketplace %s for %s",
                    name,
                    agent_profile_id,
                    exc_info=True,
                )
        plugins = [
            *(plugin.get("path", "") for plugin in profile.get("plugins", []) if isinstance(plugin, dict)),
            *(plugin for plugin in marketplace_config.get("plugins", []) if isinstance(plugin, str)),
        ]
        for plugin in filter(None, plugins):
            try:
                await self._plugin_manager.install_plugin(plugin, workspace_ref)
            except Exception:
                logger.warning(
                    "failed to install agent plugin %s for %s",
                    plugin,
                    agent_profile_id,
                    exc_info=True,
                )

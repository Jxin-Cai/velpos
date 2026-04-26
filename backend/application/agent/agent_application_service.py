from __future__ import annotations

import logging
from typing import Any

from application.memory.claude_md_revision_application_service import ClaudeMdRevisionApplicationService
from domain.project.acl.plugin_manager import PluginManager
from domain.shared.business_exception import BusinessException
from infr.agent.catalog import (
    AGENT_CATALOG,
    CATEGORIES,
    get_agent_by_id,
    read_prompt,
)

logger = logging.getLogger(__name__)


class AgentApplicationService:

    def __init__(
        self,
        plugin_manager: PluginManager | None = None,
        claude_md_revision_service: ClaudeMdRevisionApplicationService | None = None,
    ) -> None:
        self._plugin_manager = plugin_manager
        self._claude_md_revision_service = claude_md_revision_service

    async def list_agents(self, language: str = "en") -> dict[str, Any]:
        name_key = f"name_{language}" if language in ("en", "zh") else "name_en"
        desc_key = f"description_{language}" if language in ("en", "zh") else "description_en"

        categories = []
        for cat in CATEGORIES:
            agents = [
                {
                    "id": a["id"],
                    "name": a.get(name_key, a["name_en"]),
                    "description": a.get(desc_key, a["description_en"]),
                    "emoji": a["emoji"],
                    "color": a["color"],
                    "has_plugin": a.get("has_plugin", False),
                }
                for a in AGENT_CATALOG
                if a["category"] == cat["id"]
            ]
            categories.append({
                "id": cat["id"],
                "name": cat.get(name_key, cat["name_en"]),
                "agents": agents,
            })
        return {"categories": categories}

    async def load_agent(
        self,
        project_id: str,
        agent_id: str,
        language: str,
        project_repository: Any,
    ) -> Any:
        agent_meta = get_agent_by_id(agent_id)
        if not agent_meta:
            raise ValueError(f"Unknown agent: {agent_id}")

        project = await project_repository.find_by_id(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        project_dir = project.dir_path

        # If switching agents, uninstall old agent's plugins first
        current_agent = project.get_current_agent()
        if current_agent and current_agent.get("id") != agent_id:
            await self._uninstall_agent_plugins(current_agent["id"], project_dir)

        prompt_content = read_prompt(agent_id, agent_meta["category"], language)
        await self._apply_claude_md_revision(project_dir, prompt_content)
        logger.info(
            "Applied agent prompt through CLAUDE.md revision: agent=%s, lang=%s, project=%s",
            agent_id, language, project_dir,
        )

        # Install new agent's plugins
        await self._install_agent_plugins(agent_id, project_dir)

        project.load_agent(agent_id, language)
        await project_repository.save(project)
        return project

    async def unload_agent(
        self,
        project_id: str,
        project_repository: Any,
    ) -> Any:
        project = await project_repository.find_by_id(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        # Uninstall current agent's plugins
        current_agent = project.get_current_agent()
        if current_agent:
            await self._uninstall_agent_plugins(current_agent["id"], project.dir_path)

        project.unload_agent()
        await project_repository.save(project)

        await self._apply_claude_md_revision(project.dir_path, "")

        logger.info("Unloaded agent for project: %s", project_id)
        return project

    async def _apply_claude_md_revision(self, project_dir: str, content: str) -> None:
        if self._claude_md_revision_service is None:
            raise BusinessException("CLAUDE.md revision service is not configured")
        revision = await self._claude_md_revision_service.create_draft(
            project_dir=project_dir,
            content=content,
            created_by="agent",
        )
        revision = await self._claude_md_revision_service.propose(revision.id)
        revision = await self._claude_md_revision_service.approve(revision.id)
        result = await self._claude_md_revision_service.apply(
            revision_id=revision.id,
            project_dir=project_dir,
            expected_base_revision_id=revision.base_revision_id,
            expected_file_hash=revision.base_file_hash,
        )
        if result.conflict:
            raise BusinessException("CLAUDE.md changed while applying agent revision")

    async def _install_agent_plugins(self, agent_id: str, project_dir: str) -> None:
        if not self._plugin_manager:
            return
        agent_meta = get_agent_by_id(agent_id)
        if not agent_meta:
            return

        # 1. Install local plugins (from agent subdirectories)
        for plugin in agent_meta.get("plugins", []):
            try:
                await self._plugin_manager.install_plugin(plugin["path"], project_dir)
                logger.info("Installed local plugin %s for agent %s", plugin["name"], agent_id)
            except Exception:
                logger.warning(
                    "Failed to install local plugin %s for agent %s",
                    plugin["name"], agent_id, exc_info=True,
                )

        # 2. Install marketplace plugins (from config/plugins.json)
        mkt_config = agent_meta.get("marketplace_plugins", {})
        for mkt in mkt_config.get("marketplaces", []):
            name, source = mkt.get("name", ""), mkt.get("source", "")
            if not name or not source:
                continue
            if not self._plugin_manager.is_marketplace_added(name):
                try:
                    await self._plugin_manager.add_marketplace(source)
                    logger.info("Added marketplace %s (%s) for agent %s", name, source, agent_id)
                except Exception:
                    logger.warning(
                        "Failed to add marketplace %s for agent %s",
                        name, agent_id, exc_info=True,
                    )
            else:
                try:
                    await self._plugin_manager.update_marketplace(name)
                    logger.info("Updated marketplace %s for agent %s", name, agent_id)
                except Exception:
                    logger.warning(
                        "Failed to update marketplace %s for agent %s",
                        name, agent_id, exc_info=True,
                    )

        for plugin_name in mkt_config.get("plugins", []):
            try:
                # Uninstall first to ensure latest version is installed after marketplace update
                try:
                    await self._plugin_manager.uninstall_plugin(plugin_name, project_dir)
                except Exception:
                    pass  # May not be installed yet, that's fine
                await self._plugin_manager.install_plugin(plugin_name, project_dir)
                logger.info("Installed marketplace plugin %s for agent %s", plugin_name, agent_id)
            except Exception:
                logger.warning(
                    "Failed to install marketplace plugin %s for agent %s",
                    plugin_name, agent_id, exc_info=True,
                )

    async def _uninstall_agent_plugins(self, agent_id: str, project_dir: str) -> None:
        if not self._plugin_manager:
            return
        agent_meta = get_agent_by_id(agent_id)
        if not agent_meta:
            return

        # 1. Uninstall local plugins
        for plugin in agent_meta.get("plugins", []):
            try:
                await self._plugin_manager.uninstall_plugin(plugin["name"], project_dir)
                logger.info("Uninstalled local plugin %s for agent %s", plugin["name"], agent_id)
            except Exception:
                logger.warning(
                    "Failed to uninstall local plugin %s for agent %s",
                    plugin["name"], agent_id, exc_info=True,
                )

        # 2. Uninstall marketplace plugins
        mkt_config = agent_meta.get("marketplace_plugins", {})
        for plugin_name in mkt_config.get("plugins", []):
            try:
                await self._plugin_manager.uninstall_plugin(plugin_name, project_dir)
                logger.info("Uninstalled marketplace plugin %s for agent %s", plugin_name, agent_id)
            except Exception:
                logger.warning(
                    "Failed to uninstall marketplace plugin %s for agent %s",
                    plugin_name, agent_id, exc_info=True,
                )

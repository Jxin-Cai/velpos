from __future__ import annotations

import logging
from typing import Any

from domain.project.acl.plugin_manager import PluginManager

logger = logging.getLogger(__name__)


class PluginApplicationService:

    def __init__(self, plugin_manager: PluginManager) -> None:
        self._plugin_manager = plugin_manager

    async def list_plugins(self, project_dir: str) -> dict[str, Any]:
        return await self._plugin_manager.list_plugins(project_dir)

    async def install_plugin(self, plugin: str, project_dir: str) -> str:
        logger.info("Installing plugin: %s (project=%s)", plugin, project_dir)
        return await self._plugin_manager.install_plugin(plugin, project_dir)

    async def uninstall_plugin(self, plugin: str, project_dir: str) -> str:
        logger.info("Uninstalling plugin: %s (project=%s)", plugin, project_dir)
        return await self._plugin_manager.uninstall_plugin(plugin, project_dir)

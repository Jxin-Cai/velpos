from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PluginManager(ABC):

    @abstractmethod
    async def list_plugins(self, project_dir: str) -> dict[str, Any]:
        """List all plugins: available from marketplaces + installed.

        Returns a dict with:
          - available: list of plugins from all marketplaces
          - installed: list of installed plugins with scope/enabled info
        """
        ...

    @abstractmethod
    async def install_plugin(self, plugin: str, project_dir: str) -> str:
        """Install a plugin at project scope.

        Args:
            plugin: Plugin identifier (e.g. "tw-all@thoughtworks") or local path.
            project_dir: Project directory for scope=project.

        Returns:
            CLI output message.
        """
        ...

    @abstractmethod
    async def uninstall_plugin(self, plugin: str, project_dir: str) -> str:
        """Uninstall a plugin at project scope.

        Args:
            plugin: Plugin identifier (e.g. "tw-all@thoughtworks").
            project_dir: Project directory for scope=project.

        Returns:
            CLI output message.
        """
        ...

    @abstractmethod
    async def add_marketplace(self, source: str) -> str:
        """Add a plugin marketplace.

        Args:
            source: Marketplace source (GitHub repo like "owner/repo", git URL, or local path).

        Returns:
            CLI output message.
        """
        ...

    @abstractmethod
    def is_marketplace_added(self, name: str) -> bool:
        """Check if a marketplace is already configured.

        Args:
            name: Marketplace name (e.g. "thoughtworks").
        """
        ...

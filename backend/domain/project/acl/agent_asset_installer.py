from __future__ import annotations

from abc import ABC, abstractmethod


class AgentAssetInstaller(ABC):
    """Applies agent-selected MCP servers and skills to a project workspace."""

    @abstractmethod
    async def apply_mcp_servers(self, project_dir: str, servers: dict[str, dict]) -> None:
        """Merge the given MCP servers (name -> server config) into the project MCP config."""
        ...

    @abstractmethod
    async def remove_mcp_servers(self, project_dir: str, names: list[str]) -> None:
        """Remove the given MCP servers by name from the project MCP config."""
        ...

    @abstractmethod
    async def install_skill(self, project_dir: str, name: str, content: str) -> None:
        """Write a skill's SKILL.md into the project skills directory."""
        ...

    @abstractmethod
    async def uninstall_skill(self, project_dir: str, name: str) -> None:
        """Remove a previously installed skill from the project skills directory."""
        ...

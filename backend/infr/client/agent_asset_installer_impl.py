from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from pathlib import Path

from domain.project.acl.agent_asset_installer import AgentAssetInstaller

logger = logging.getLogger(__name__)

_MCP_CONFIG_FILE = ".mcp.json"
_SKILLS_DIR = Path(".claude") / "skills"
_SAFE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class FilesystemAgentAssetInstaller(AgentAssetInstaller):
    """Writes MCP server configs to <project>/.mcp.json and skills to <project>/.claude/skills/."""

    async def apply_mcp_servers(self, project_dir: str, servers: dict[str, dict]) -> None:
        if not servers:
            return
        await asyncio.to_thread(self._merge_mcp_config, project_dir, servers)

    async def remove_mcp_servers(self, project_dir: str, names: list[str]) -> None:
        if not names:
            return
        await asyncio.to_thread(self._prune_mcp_config, project_dir, names)

    async def install_skill(self, project_dir: str, name: str, content: str) -> None:
        skill_dir = self._skill_dir(project_dir, name)
        await asyncio.to_thread(self._write_skill, skill_dir, content)

    async def uninstall_skill(self, project_dir: str, name: str) -> None:
        skill_dir = self._skill_dir(project_dir, name)
        await asyncio.to_thread(self._remove_skill, skill_dir)

    @staticmethod
    def _skill_dir(project_dir: str, name: str) -> Path:
        if not _SAFE_NAME_PATTERN.match(name):
            raise ValueError(f"Unsafe skill name: {name!r}")
        return Path(project_dir) / _SKILLS_DIR / name

    def _merge_mcp_config(self, project_dir: str, servers: dict[str, dict]) -> None:
        config_path = Path(project_dir) / _MCP_CONFIG_FILE
        config = self._read_mcp_config(config_path)
        mcp_servers = config.setdefault("mcpServers", {})
        mcp_servers.update(servers)
        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _prune_mcp_config(self, project_dir: str, names: list[str]) -> None:
        config_path = Path(project_dir) / _MCP_CONFIG_FILE
        if not config_path.exists():
            return
        config = self._read_mcp_config(config_path)
        mcp_servers = config.get("mcpServers", {})
        for name in names:
            mcp_servers.pop(name, None)
        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _read_mcp_config(config_path: Path) -> dict:
        if not config_path.exists():
            return {}
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in %s, rebuilding MCP config", config_path, exc_info=True)
            return {}
        if not isinstance(loaded, dict):
            logger.warning("Unexpected MCP config shape in %s, rebuilding", config_path)
            return {}
        return loaded

    @staticmethod
    def _write_skill(skill_dir: Path, content: str) -> None:
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    @staticmethod
    def _remove_skill(skill_dir: Path) -> None:
        if skill_dir.is_dir():
            shutil.rmtree(skill_dir)

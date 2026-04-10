from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from domain.project.acl.plugin_manager import PluginManager as PluginManagerPort

logger = logging.getLogger(__name__)


class ClaudePluginManager(PluginManagerPort):

    def __init__(self, cli_path: str | None = None) -> None:
        self._cli_path = cli_path or os.getenv("CLAUDE_CLI_PATH")
        if not self._cli_path:
            raise RuntimeError("CLAUDE_CLI_PATH environment variable is not set")
        self._claude_dir = Path(os.getenv("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
        self._plugins_dir = self._claude_dir / "plugins"

    async def list_plugins(self, project_dir: str) -> dict[str, Any]:
        available = self._read_available_plugins()
        installed = self._read_installed_plugins()
        project_enabled = self._read_project_enabled(project_dir)
        user_enabled = self._read_user_enabled()

        plugins: list[dict[str, Any]] = []
        seen_keys: set[str] = set()

        # 1. Process installed plugins from installed_plugins.json
        for plugin_key, installs in installed.items():
            name, marketplace = self._parse_plugin_key(plugin_key)
            avail_info = next(
                (a for a in available if a["name"] == name and a["marketplace"] == marketplace),
                {},
            )
            for install_info in installs:
                scope = install_info.get("scope", "user")
                is_project_scoped = (
                    scope == "project"
                    and install_info.get("projectPath", "") == project_dir
                )
                is_user_scoped = scope == "user"

                if not is_project_scoped and not is_user_scoped:
                    continue

                enabled = False
                if is_project_scoped:
                    enabled = project_enabled.get(plugin_key, False)
                elif is_user_scoped:
                    enabled = user_enabled.get(plugin_key, False)

                plugins.append({
                    "name": name,
                    "marketplace": marketplace,
                    "key": plugin_key,
                    "description": avail_info.get("description", ""),
                    "version": install_info.get("version", ""),
                    "scope": scope,
                    "enabled": enabled,
                    "installed": True,
                })
                seen_keys.add(plugin_key)

        # 2. Check project enabledPlugins for plugins not in installed_plugins.json
        #    (project settings may reference plugins by marketplace name)
        for enabled_key, is_enabled in project_enabled.items():
            if enabled_key in seen_keys:
                continue
            name, marketplace = self._parse_plugin_key(enabled_key)
            avail_info = next(
                (a for a in available if a["name"] == name and a["marketplace"] == marketplace),
                {},
            )
            # Verify via cache directory
            cache_dir = self._plugins_dir / "cache" / marketplace / name
            if cache_dir.exists():
                version = ""
                for ver_dir in sorted(cache_dir.iterdir(), reverse=True):
                    if ver_dir.is_dir():
                        version = ver_dir.name
                        break
                plugins.append({
                    "name": name,
                    "marketplace": marketplace,
                    "key": enabled_key,
                    "description": avail_info.get("description", ""),
                    "version": version,
                    "scope": "project",
                    "enabled": is_enabled,
                    "installed": True,
                })
                seen_keys.add(enabled_key)

        # 3. Add available but not yet installed plugins
        for avail in available:
            key = f"{avail['name']}@{avail['marketplace']}"
            if key in seen_keys:
                continue
            plugins.append({
                "name": avail["name"],
                "marketplace": avail["marketplace"],
                "key": key,
                "description": avail.get("description", ""),
                "version": avail.get("version", ""),
                "scope": "",
                "enabled": False,
                "installed": False,
            })
            seen_keys.add(key)

        return {"plugins": plugins}

    async def install_plugin(self, plugin: str, project_dir: str) -> str:
        return await self._run_cli(
            ["plugin", "install", plugin, "-s", "project"],
            cwd=project_dir,
        )

    async def uninstall_plugin(self, plugin: str, project_dir: str) -> str:
        return await self._run_cli(
            ["plugin", "uninstall", plugin, "-s", "project"],
            cwd=project_dir,
        )

    async def add_marketplace(self, source: str) -> str:
        return await self._run_cli(
            ["plugin", "marketplace", "add", source],
            cwd=str(Path.home()),
        )

    async def update_marketplace(self, name: str | None = None) -> str:
        args = ["plugin", "marketplace", "update"]
        if name:
            args.append(name)
        return await self._run_cli(args, cwd=str(Path.home()))

    def is_marketplace_added(self, name: str) -> bool:
        marketplaces_json = self._plugins_dir / "known_marketplaces.json"
        if not marketplaces_json.exists():
            return False
        try:
            data = json.loads(marketplaces_json.read_text())
            return name in data
        except (json.JSONDecodeError, OSError):
            return False

    async def _run_cli(self, args: list[str], cwd: str) -> str:
        cmd = [self._cli_path, *args]
        logger.info("Running CLI command: %s (cwd=%s)", " ".join(cmd), cwd)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode().strip()
        err_output = stderr.decode().strip()

        if proc.returncode != 0:
            logger.error("CLI command failed: %s, stderr: %s", " ".join(cmd), err_output)
            raise RuntimeError(f"CLI command failed: {err_output or output}")

        logger.info("CLI command succeeded: %s", output[:200])
        return output or "OK"

    def _read_available_plugins(self) -> list[dict[str, Any]]:
        """Read all plugins from known marketplaces."""
        result: list[dict[str, Any]] = []
        marketplaces_json = self._plugins_dir / "known_marketplaces.json"
        if not marketplaces_json.exists():
            return result

        try:
            data = json.loads(marketplaces_json.read_text())
        except (json.JSONDecodeError, OSError):
            return result

        for mkt_name, mkt_info in data.items():
            install_location = mkt_info.get("installLocation", "")
            if not install_location:
                continue
            manifest_path = Path(install_location) / ".claude-plugin" / "marketplace.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            for plugin in manifest.get("plugins", []):
                result.append({
                    "name": plugin.get("name", ""),
                    "marketplace": mkt_name,
                    "description": plugin.get("description", ""),
                    "version": plugin.get("version", ""),
                })

        return result

    def _read_installed_plugins(self) -> dict[str, list[dict[str, Any]]]:
        """Read installed_plugins.json."""
        path = self._plugins_dir / "installed_plugins.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text())
            return data.get("plugins", {})
        except (json.JSONDecodeError, OSError):
            return {}

    def _read_project_enabled(self, project_dir: str) -> dict[str, bool]:
        """Read enabledPlugins from project's .claude/settings.json."""
        if not project_dir:
            return {}
        path = Path(project_dir) / ".claude" / "settings.json"
        return self._read_enabled_plugins(path)

    def _read_user_enabled(self) -> dict[str, bool]:
        """Read enabledPlugins from user's ~/.claude/settings.json."""
        path = self._claude_dir / "settings.json"
        return self._read_enabled_plugins(path)

    @staticmethod
    def _read_enabled_plugins(path: Path) -> dict[str, bool]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text())
            return data.get("enabledPlugins", {})
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _parse_plugin_key(key: str) -> tuple[str, str]:
        """Parse 'name@marketplace' into (name, marketplace)."""
        if "@" in key:
            parts = key.split("@", 1)
            return parts[0], parts[1]
        return key, ""

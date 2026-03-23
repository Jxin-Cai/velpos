from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class SettingsFileService:
    """Read and write ~/.claude/settings.json."""

    def __init__(self) -> None:
        self._settings_path = Path.home() / ".claude" / "settings.json"

    # Default settings values — merged on read, user can override
    _DEFAULTS: dict = {
        "hasCompletedOnboarding": True,
    }

    async def read_settings(self) -> dict:
        """Read ~/.claude/settings.json and return its contents as a dict.

        Merges _DEFAULTS for any missing keys (user overrides take precedence).
        Returns defaults if the file does not exist or contains invalid JSON.
        """
        try:
            data = await asyncio.to_thread(self._read_sync)
        except FileNotFoundError:
            data = {}
        except json.JSONDecodeError:
            logger.warning(
                "settings.json contains invalid JSON, returning defaults: %s",
                self._settings_path,
            )
            data = {}

        # Apply defaults for missing keys
        for key, default_val in self._DEFAULTS.items():
            if key not in data:
                data[key] = default_val

        return data

    async def write_settings(self, data: dict) -> None:
        """Write a complete dict to ~/.claude/settings.json.

        Creates the ~/.claude/ directory if it does not exist.
        Uses a temporary file + os.replace for atomic write safety.

        Raises OSError on write failure.
        """
        try:
            await asyncio.to_thread(self._write_sync, data)
        except OSError:
            logger.error(
                "Failed to write settings.json: %s",
                self._settings_path,
                exc_info=True,
            )
            raise

    async def update_env_section(self, env_vars: dict[str, str]) -> None:
        """Merge-update the 'env' section in settings.json.

        Reads the current settings, updates (not replaces) the 'env'
        key with the provided env_vars, and writes the result back.
        Existing keys not present in env_vars are preserved.
        """
        settings = await self.read_settings()
        existing_env: dict = settings.get("env", {})
        existing_env.update(env_vars)
        settings["env"] = existing_env
        await self.write_settings(settings)

    def _read_sync(self) -> dict:
        """Synchronous file read, intended to be called via asyncio.to_thread."""
        text = self._settings_path.read_text(encoding="utf-8")
        return json.loads(text)

    def _write_sync(self, data: dict) -> None:
        """Synchronous atomic file write, intended to be called via asyncio.to_thread."""
        parent = self._settings_path.parent
        parent.mkdir(parents=True, exist_ok=True)

        content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"

        fd, tmp_path = tempfile.mkstemp(
            dir=str(parent),
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, str(self._settings_path))
        except BaseException:
            # Clean up the temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

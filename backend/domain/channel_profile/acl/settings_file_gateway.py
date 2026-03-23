from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SettingsFileGateway(ABC):

    @abstractmethod
    async def read_settings(self) -> dict[str, Any]:
        """Read ~/.claude/settings.json and parse to dict.

        Returns an empty dict if the file does not exist.
        """
        ...

    @abstractmethod
    async def write_settings(self, data: dict[str, Any]) -> None:
        """Serialize the complete dict as JSON and write to ~/.claude/settings.json.

        Should use an atomic write strategy (write to a temp file then rename).
        """
        ...

    @abstractmethod
    async def update_env_section(self, env_vars: dict[str, str]) -> None:
        """Merge env_vars into the top-level "env" field of settings.json.

        Reads the current settings.json, merges env_vars into the "env" section
        (preserving other keys already present in env), then writes back the file.
        """
        ...

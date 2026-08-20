from __future__ import annotations

from typing import Any

from application.session.native_otel_config import (
    build_claude_code_shared_env,
    build_persistable_otel_destination_env,
)
from domain.channel_profile.acl.settings_file_gateway import SettingsFileGateway
from infr.client.claude_settings_env import CLAUDE_CODE_GENERAL_ENV_DEFAULTS


class SettingsApplicationService:

    def __init__(
        self,
        settings_file_gateway: SettingsFileGateway,
    ) -> None:
        self._settings_file_gateway = settings_file_gateway

    async def get_settings(self) -> dict[str, Any]:
        """Read the complete settings.json content."""
        settings = await self._settings_file_gateway.read_settings()
        raw_env = settings.get("env")
        settings["env"] = build_claude_code_shared_env(
            raw_env if isinstance(raw_env, dict) else None
        )
        return settings

    async def update_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        """Write data to settings.json and return the written content.

        Writes the full data dict, then re-reads to confirm the write succeeded.
        """
        env = data.get("env")
        if isinstance(env, dict):
            data = {**data, "env": _with_shared_claude_code_env(env)}
        await self._settings_file_gateway.write_settings(data)
        return await self.get_settings()

    async def update_env_section(self, env_vars: dict[str, str]) -> None:
        """Update the env section of settings.json with the given variables."""
        await self._settings_file_gateway.update_env_section(env_vars)

    async def ensure_shared_env(self) -> dict[str, Any]:
        """Persist Claude Code audit defaults and OTLP destination to settings.json.

        Missing collection switches are filled in; existing user opt-outs are
        preserved. The Velpos-owned OTLP destination is always refreshed so
        pro's isolated ~/.claude matches the SDK subprocess environment.
        """
        settings = await self._settings_file_gateway.read_settings()
        existing_env = settings.get("env")
        if not isinstance(existing_env, dict):
            existing_env = {}
        patch: dict[str, str] = {}
        for key, value in CLAUDE_CODE_GENERAL_ENV_DEFAULTS.items():
            current = existing_env.get(key)
            if not isinstance(current, str):
                patch[key] = value
        patch.update(build_persistable_otel_destination_env())
        if patch:
            await self._settings_file_gateway.update_env_section(patch)
        return await self.get_settings()


def _with_shared_claude_code_env(env: dict[str, Any]) -> dict[str, str]:
    merged = {
        key: value
        for key, value in env.items()
        if isinstance(key, str) and isinstance(value, str)
    }
    for key, value in CLAUDE_CODE_GENERAL_ENV_DEFAULTS.items():
        merged.setdefault(key, value)
    merged.update(build_persistable_otel_destination_env())
    return merged

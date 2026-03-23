from __future__ import annotations

from typing import Any

from domain.channel_profile.acl.settings_file_gateway import SettingsFileGateway


class SettingsApplicationService:

    def __init__(
        self,
        settings_file_gateway: SettingsFileGateway,
    ) -> None:
        self._settings_file_gateway = settings_file_gateway

    async def get_settings(self) -> dict[str, Any]:
        """Read the complete settings.json content."""
        return await self._settings_file_gateway.read_settings()

    async def update_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        """Write data to settings.json and return the written content.

        Writes the full data dict, then re-reads to confirm the write succeeded.
        """
        await self._settings_file_gateway.write_settings(data)
        return await self._settings_file_gateway.read_settings()

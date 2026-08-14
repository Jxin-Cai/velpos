from __future__ import annotations

import pytest

from application.settings.settings_application_service import SettingsApplicationService
from infr.client.claude_settings_env import CLAUDE_CODE_GENERAL_ENV_DEFAULTS


class _SettingsGatewayStub:
    async def read_settings(self) -> dict:
        return {"env": {"ANTHROPIC_MODEL": "claude-sonnet-5"}}

    async def write_settings(self, data: dict) -> None:
        return None

    async def update_env_section(self, env_vars: dict[str, str]) -> None:
        return None


@pytest.mark.asyncio
async def test_full_audit_defaults_exposed_in_claude_code_general_settings() -> None:
    # Arrange
    service = SettingsApplicationService(_SettingsGatewayStub())  # type: ignore[arg-type]

    # Act
    settings = await service.get_settings()

    # Assert
    assert settings["env"] == {
        **CLAUDE_CODE_GENERAL_ENV_DEFAULTS,
        "ANTHROPIC_MODEL": "claude-sonnet-5",
    }

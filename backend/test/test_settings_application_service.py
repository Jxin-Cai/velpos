from __future__ import annotations

import pytest

from application.settings.settings_application_service import SettingsApplicationService
from infr.client.claude_settings_env import CLAUDE_CODE_GENERAL_ENV_DEFAULTS


class _SettingsGatewayStub:
    def __init__(self, settings: dict | None = None) -> None:
        self.settings = settings or {"env": {"ANTHROPIC_MODEL": "claude-sonnet-5"}}
        self.updated_env: dict[str, str] | None = None

    async def read_settings(self) -> dict:
        return {
            key: (dict(value) if isinstance(value, dict) else value)
            for key, value in self.settings.items()
        }

    async def write_settings(self, data: dict) -> None:
        self.settings = data

    async def update_env_section(self, env_vars: dict[str, str]) -> None:
        env = dict(self.settings.get("env") or {})
        env.update(env_vars)
        self.settings["env"] = env
        self.updated_env = env_vars


@pytest.mark.asyncio
async def test_exposes_general_audit_defaults_when_settings_only_have_model(
    monkeypatch,
) -> None:
    # Arrange
    monkeypatch.setenv("VELPOS_NATIVE_OTEL_ENABLED", "false")
    service = SettingsApplicationService(_SettingsGatewayStub())  # type: ignore[arg-type]

    # Act
    settings = await service.get_settings()

    # Assert
    assert settings["env"] == {
        **CLAUDE_CODE_GENERAL_ENV_DEFAULTS,
        "ANTHROPIC_MODEL": "claude-sonnet-5",
    }


@pytest.mark.asyncio
async def test_exposes_otlp_destination_when_native_otel_is_enabled(monkeypatch) -> None:
    # Arrange
    monkeypatch.setenv("VELPOS_NATIVE_OTEL_ENABLED", "true")
    monkeypatch.setenv("VELPOS_OTEL_ENDPOINT", "http://127.0.0.1:8083/api/otel")
    service = SettingsApplicationService(_SettingsGatewayStub())  # type: ignore[arg-type]

    # Act
    settings = await service.get_settings()

    # Assert
    assert settings["env"]["OTEL_TRACES_EXPORTER"] == "otlp"
    assert settings["env"]["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/json"
    assert settings["env"]["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://127.0.0.1:8083/api/otel"


@pytest.mark.asyncio
async def test_persists_general_audit_defaults_when_settings_missing_them(
    monkeypatch,
) -> None:
    # Arrange
    monkeypatch.setenv("VELPOS_NATIVE_OTEL_ENABLED", "false")
    gateway = _SettingsGatewayStub({"env": {"ANTHROPIC_MODEL": "claude-sonnet-5"}})
    service = SettingsApplicationService(gateway)  # type: ignore[arg-type]

    # Act
    await service.ensure_shared_env()

    # Assert
    assert gateway.settings["env"]["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"


@pytest.mark.asyncio
async def test_persists_otlp_destination_when_ensuring_shared_env(monkeypatch) -> None:
    # Arrange
    monkeypatch.setenv("VELPOS_NATIVE_OTEL_ENABLED", "true")
    monkeypatch.setenv("VELPOS_OTEL_ENDPOINT", "http://127.0.0.1:8083/api/otel")
    gateway = _SettingsGatewayStub({"env": {"ANTHROPIC_MODEL": "claude-sonnet-5"}})
    service = SettingsApplicationService(gateway)  # type: ignore[arg-type]

    # Act
    await service.ensure_shared_env()

    # Assert
    assert gateway.settings["env"]["OTEL_EXPORTER_OTLP_ENDPOINT"] == (
        "http://127.0.0.1:8083/api/otel"
    )


@pytest.mark.asyncio
async def test_preserves_audit_opt_out_when_ensuring_shared_env(monkeypatch) -> None:
    # Arrange
    monkeypatch.setenv("VELPOS_NATIVE_OTEL_ENABLED", "true")
    gateway = _SettingsGatewayStub({"env": {"OTEL_LOG_RAW_API_BODIES": "0"}})
    service = SettingsApplicationService(gateway)  # type: ignore[arg-type]

    # Act
    await service.ensure_shared_env()

    # Assert
    assert gateway.settings["env"]["OTEL_LOG_RAW_API_BODIES"] == "0"


@pytest.mark.asyncio
async def test_writes_otlp_destination_when_updating_settings(monkeypatch) -> None:
    # Arrange
    monkeypatch.setenv("VELPOS_NATIVE_OTEL_ENABLED", "true")
    monkeypatch.setenv("VELPOS_OTEL_ENDPOINT", "http://127.0.0.1:8083/api/otel")
    gateway = _SettingsGatewayStub()
    service = SettingsApplicationService(gateway)  # type: ignore[arg-type]

    # Act
    await service.update_settings({"env": {"ANTHROPIC_MODEL": "claude-sonnet-5"}})

    # Assert
    assert gateway.settings["env"]["OTEL_TRACES_EXPORTER"] == "otlp"

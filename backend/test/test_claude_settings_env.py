from __future__ import annotations

import json

import pytest

import infr.client.claude_agent_gateway as claude_agent_gateway_module
import infr.client.claude_command_gateway as claude_command_gateway_module
from infr.client.claude_agent_gateway import ClaudeAgentGateway
from infr.client.claude_command_gateway import ClaudeCommandGateway
from infr.client.claude_settings_env import load_claude_settings_env


def test_loads_env_when_user_settings_define_environment_variables(tmp_path) -> None:
    # Arrange
    settings = {"env": {"ANTHROPIC_API_KEY": "secret", "API_TIMEOUT_MS": "60000"}}
    (tmp_path / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    # Act
    env = load_claude_settings_env(tmp_path)

    # Assert
    assert env == settings["env"]


def test_returns_empty_env_when_user_settings_do_not_exist(tmp_path) -> None:
    # Arrange / Act
    env = load_claude_settings_env(tmp_path)

    # Assert
    assert env == {}


def test_returns_empty_env_when_user_settings_contain_invalid_json(tmp_path) -> None:
    # Arrange
    (tmp_path / "settings.json").write_text("{invalid", encoding="utf-8")

    # Act
    env = load_claude_settings_env(tmp_path)

    # Assert
    assert env == {}


def test_ignores_non_string_entries_when_settings_env_contains_invalid_values(tmp_path) -> None:
    # Arrange
    settings = {"env": {"ANTHROPIC_API_KEY": "secret", "RETRIES": 3}}
    (tmp_path / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    # Act
    env = load_claude_settings_env(tmp_path)

    # Assert
    assert env == {"ANTHROPIC_API_KEY": "secret"}


def test_uses_claude_config_dir_when_environment_overrides_default_path(
    tmp_path,
    monkeypatch,
) -> None:
    # Arrange
    settings = {"env": {"ANTHROPIC_AUTH_TOKEN": "token"}}
    (tmp_path / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))

    # Act
    env = load_claude_settings_env()

    # Assert
    assert env == settings["env"]


@pytest.mark.asyncio
async def test_injects_settings_env_when_agent_gateway_starts_sdk_client(
    monkeypatch,
) -> None:
    # Arrange
    expected_env = {"ANTHROPIC_AUTH_TOKEN": "token"}
    captured_options: dict = {}

    class _OptionsStub:
        def __init__(self, **kwargs) -> None:
            captured_options.update(kwargs)

    class _ClientStub:
        def __init__(self, options) -> None:
            self.options = options

        async def connect(self) -> None:
            return None

    monkeypatch.setattr(
        claude_agent_gateway_module,
        "load_claude_settings_env",
        lambda: expected_env,
    )
    monkeypatch.setattr(claude_agent_gateway_module, "ClaudeAgentOptions", _OptionsStub)
    monkeypatch.setattr(claude_agent_gateway_module, "ClaudeSDKClient", _ClientStub)
    gateway = ClaudeAgentGateway(cli_path="/usr/local/bin/claude")

    # Act
    await gateway._try_connect(
        session_id="session-1",
        model="claude-sonnet-4-6",
        perm_mode="acceptEdits",
        cwd="/tmp/project",
        prev_sdk_sid=None,
    )

    # Assert
    assert captured_options["env"] == expected_env

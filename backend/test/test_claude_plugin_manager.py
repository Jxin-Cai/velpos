from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, call

import pytest

from infr.client.claude_plugin_manager import ClaudePluginManager


@pytest.mark.asyncio
async def test_reinstalls_plugin_after_marketplace_refresh_when_plugin_is_upgraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    manager = object.__new__(ClaudePluginManager)
    run_cli = AsyncMock(side_effect=["marketplace refreshed", "removed", "installed"])
    monkeypatch.setattr(manager, "_run_cli", run_cli)

    # Act
    await manager.upgrade_plugin("reviewer@team-market", "/workspace/project")

    # Assert
    assert run_cli.await_args_list == [
        call(
            ["plugin", "marketplace", "update", "team-market"],
            cwd=str(Path.home()),
            extra_env=None,
        ),
        call(
            ["plugin", "uninstall", "reviewer@team-market", "-s", "project"],
            cwd="/workspace/project",
        ),
        call(
            ["plugin", "install", "reviewer@team-market", "-s", "project"],
            cwd="/workspace/project",
        ),
    ]


@pytest.mark.asyncio
async def test_keeps_installed_plugin_when_marketplace_refresh_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    manager = object.__new__(ClaudePluginManager)
    run_cli = AsyncMock(side_effect=RuntimeError("refresh failed"))
    monkeypatch.setattr(manager, "_run_cli", run_cli)

    # Act
    with pytest.raises(RuntimeError, match="refresh failed"):
        await manager.upgrade_plugin("reviewer@team-market", "/workspace/project")

    # Assert
    run_cli.assert_awaited_once_with(
        ["plugin", "marketplace", "update", "team-market"],
        cwd=str(Path.home()),
        extra_env=None,
    )


@pytest.mark.asyncio
async def test_refreshes_shared_marketplace_once_when_all_plugins_are_upgraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    manager = object.__new__(ClaudePluginManager)
    monkeypatch.setattr(
        manager,
        "_read_installed_plugins",
        lambda: {
            "reviewer@team-market": [
                {"scope": "project", "projectPath": "/workspace/project"}
            ],
            "designer@team-market": [
                {"scope": "project", "projectPath": "/workspace/project"}
            ],
        },
    )
    monkeypatch.setattr(manager, "_read_project_enabled", lambda _project_dir: {})
    run_cli = AsyncMock(return_value="OK")
    monkeypatch.setattr(manager, "_run_cli", run_cli)

    # Act
    await manager.upgrade_all_plugins("/workspace/project")

    # Assert
    commands = [call.args[0] for call in run_cli.await_args_list]
    assert commands.count(
        ["plugin", "marketplace", "update", "team-market"]
    ) == 1
    assert [
        "plugin",
        "update",
        "reviewer@team-market",
        "-s",
        "project",
    ] not in commands
    assert ["plugin", "install", "reviewer@team-market", "-s", "project"] in commands
    assert ["plugin", "install", "designer@team-market", "-s", "project"] in commands

import json
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from infr.workspace.filesystem_workspace_gateway import FilesystemWorkspaceGateway


def _create_project(project: Path) -> None:
    (project / ".claude" / "rules").mkdir(parents=True)
    (project / "CLAUDE.md").write_text("# Project instructions\n", encoding="utf-8")
    (project / ".claude" / "rules" / "python.md").write_text(
        "Use Python.\n", encoding="utf-8"
    )
    (project / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "enabledPlugins": {
                    "allowed@market": True,
                    "disabled@market": False,
                },
                "env": {"ANTHROPIC_API_KEY": "secret-key"},
                "permissions": {"allow": ["Bash(*)"]},
                "pluginConfigs": {"allowed@market": {"token": "secret-token"}},
            }
        ),
        encoding="utf-8",
    )
    (project / ".claude" / "settings.local.json").write_text(
        json.dumps({"env": {"TOKEN": "local-secret"}}), encoding="utf-8"
    )
    (project / ".env").write_text("TOKEN=env-secret\n", encoding="utf-8")


def _manifest(workspace: Path) -> dict[str, object]:
    return json.loads(
        (workspace / ".velpos" / "agent-manifest.json").read_text(encoding="utf-8")
    )


def test_creates_slot_and_execution_layout_when_source_configuration_exists(
    tmp_path: Path,
) -> None:
    # Arrange
    project = tmp_path / "project"
    team_root = tmp_path / "teams"
    _create_project(project)
    gateway = FilesystemWorkspaceGateway()

    # Act
    workspace = Path(
        gateway.create_independent_workspace(
            str(team_root),
            "Product Team",
            "Backend Agent",
            str(project),
            "profiles/backend",
        )
    )
    execution = Path(gateway.create_execution_workspace(str(workspace), "Run 001"))

    # Assert
    assert workspace == team_root / "product-team-backend-agent"
    assert (workspace / "executions").is_dir()
    assert (workspace / "CLAUDE.md").read_text() == "# Project instructions\n"
    assert (workspace / ".claude" / "rules" / "python.md").is_file()
    assert execution == workspace / "executions" / "run-001"
    assert (execution / "CLAUDE.md").is_file()
    assert (execution / ".claude" / "rules" / "python.md").is_file()
    assert stat.S_IMODE((execution / "CLAUDE.md").stat().st_mode) == 0o444
    assert _manifest(workspace)["agent_profile_ref"] == "profiles/backend"


def test_isolates_execution_workspaces_when_created_concurrently(tmp_path: Path) -> None:
    # Arrange
    project = tmp_path / "project"
    _create_project(project)
    gateway = FilesystemWorkspaceGateway()
    workspace = gateway.create_independent_workspace(
        str(tmp_path / "teams"), "team", "slot", str(project)
    )

    # Act
    with ThreadPoolExecutor(max_workers=8) as executor:
        paths = list(
            executor.map(
                lambda index: gateway.create_execution_workspace(
                    workspace, f"execution-{index}"
                ),
                range(16),
            )
        )

    # Assert
    assert len(set(paths)) == 16
    assert all(Path(path).parent.name == "executions" for path in paths)
    assert all((Path(path) / "CLAUDE.md").is_file() for path in paths)


def test_copies_only_allowed_plugin_settings_when_source_contains_secrets(
    tmp_path: Path,
) -> None:
    # Arrange
    project = tmp_path / "project"
    _create_project(project)
    gateway = FilesystemWorkspaceGateway()

    # Act
    workspace = Path(
        gateway.create_independent_workspace(
            str(tmp_path / "teams"), "team", "slot", str(project)
        )
    )
    copied_settings = json.loads(
        (workspace / ".claude" / "settings.json").read_text(encoding="utf-8")
    )

    # Assert
    assert copied_settings == {
        "enabledPlugins": {
            "allowed@market": True,
            "disabled@market": False,
        }
    }
    assert not (workspace / ".claude" / "settings.local.json").exists()
    assert not (workspace / ".env").exists()
    assert "secret" not in json.dumps(copied_settings)


def test_loads_agent_prompt_and_plugins_when_profile_exists(tmp_path: Path) -> None:
    # Arrange
    project = tmp_path / "project"
    _create_project(project)
    gateway = FilesystemWorkspaceGateway()

    # Act
    workspace = Path(
        gateway.create_independent_workspace(
            str(tmp_path / "teams"),
            "delivery",
            "backend",
            str(project),
            "backend-architect",
        )
    )
    settings = json.loads(
        (workspace / ".claude" / "settings.json").read_text(encoding="utf-8")
    )

    # Assert
    claude_md = (workspace / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Backend Architect Workbench Agent" in claude_md
    assert "# Project Instructions" in claude_md
    assert settings["enabledPlugins"]["backend-architect@agents-plugin"] is True
    assert "backend-architect@agents-plugin" in _manifest(workspace)["plugin_references"]


def test_rejects_traversal_and_symlink_escape_when_resolving_destinations(
    tmp_path: Path,
) -> None:
    # Arrange
    project = tmp_path / "project"
    team_root = tmp_path / "teams"
    outside = tmp_path / "outside"
    _create_project(project)
    team_root.mkdir()
    outside.mkdir()
    gateway = FilesystemWorkspaceGateway()

    # Act / Assert
    with pytest.raises(ValueError, match="invalid team_slug"):
        gateway.create_independent_workspace(
            str(team_root), "../team", "slot", str(project)
        )

    (team_root / "team-slot").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="workspace path cannot be a symlink"):
        gateway.create_independent_workspace(
            str(team_root), "team", "slot", str(project)
        )


def test_rejects_execution_symlink_escape_when_target_already_exists(
    tmp_path: Path,
) -> None:
    # Arrange
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    _create_project(project)
    outside.mkdir()
    gateway = FilesystemWorkspaceGateway()
    workspace = Path(
        gateway.create_independent_workspace(
            str(tmp_path / "teams"), "team", "slot", str(project)
        )
    )
    (workspace / "executions" / "escape").symlink_to(
        outside, target_is_directory=True
    )

    # Act / Assert
    with pytest.raises(ValueError, match="cannot be a symlink"):
        gateway.create_execution_workspace(str(workspace), "escape")


def test_rolls_back_only_staging_directory_when_manifest_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    project = tmp_path / "project"
    team_root = tmp_path / "teams"
    preexisting = team_root / "keep-me"
    _create_project(project)
    preexisting.mkdir(parents=True)
    (preexisting / "data.txt").write_text("keep", encoding="utf-8")
    gateway = FilesystemWorkspaceGateway()

    def fail_write(path: Path, value: dict[str, object]) -> None:
        raise OSError("simulated manifest failure")

    monkeypatch.setattr(FilesystemWorkspaceGateway, "_atomic_write_json", fail_write)

    # Act / Assert
    with pytest.raises(OSError, match="simulated manifest failure"):
        gateway.create_independent_workspace(
            str(team_root), "team", "slot", str(project)
        )
    assert (preexisting / "data.txt").read_text() == "keep"
    assert not (team_root / "team-slot").exists()
    assert list(team_root.glob(".workspace-*")) == []


def test_produces_stable_manifest_hash_when_allowed_source_is_unchanged(
    tmp_path: Path,
) -> None:
    # Arrange
    project = tmp_path / "project"
    _create_project(project)

    # Act
    first_gateway = FilesystemWorkspaceGateway()
    first = Path(
        first_gateway.create_independent_workspace(
            str(tmp_path / "teams-a"), "team", "slot", str(project)
        )
    )
    (project / ".env").write_text("TOKEN=changed-secret\n", encoding="utf-8")
    second_gateway = FilesystemWorkspaceGateway()
    second = Path(
        second_gateway.create_independent_workspace(
            str(tmp_path / "teams-b"), "team", "slot", str(project)
        )
    )

    # Assert
    assert _manifest(first)["source_config_hash"] == _manifest(second)[
        "source_config_hash"
    ]


def test_detects_collision_when_distinct_refs_normalize_to_same_slug(
    tmp_path: Path,
) -> None:
    # Arrange
    project = tmp_path / "project"
    team_root = tmp_path / "teams"
    _create_project(project)
    gateway = FilesystemWorkspaceGateway()
    gateway.create_independent_workspace(
        str(team_root), "Team A", "Slot", str(project)
    )

    # Act / Assert
    with pytest.raises(FileExistsError, match="different source or identity"):
        gateway.create_independent_workspace(
            str(team_root), "team-a", "slot", str(project)
        )

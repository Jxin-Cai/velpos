from __future__ import annotations

import re
from pathlib import Path

import pytest

from application.project.workspace_directory import (
    create_workspace_directory,
    default_agent_workspace_root,
    default_team_workspace_root,
    github_repository_name,
)


def test_creates_random_child_directory_when_root_is_provided(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "project-root"

    # Act
    workspace = create_workspace_directory(str(root))

    # Assert
    assert workspace.parent == root
    assert workspace.is_dir()
    assert re.fullmatch(r"[0-9a-f]{8}", workspace.name)


def test_creates_distinct_directories_when_called_twice(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "project-root"

    # Act
    first = create_workspace_directory(str(root))
    second = create_workspace_directory(str(root))

    # Assert
    assert first != second


def test_rejects_project_directory_when_path_is_blank() -> None:
    # Arrange
    root = "   "

    # Act / Assert
    with pytest.raises(ValueError, match="Project directory is required"):
        create_workspace_directory(root)


@pytest.mark.parametrize(
    ("github_url", "expected"),
    [
        ("https://github.com/openai/codex.git", "codex"),
        ("git@github.com:openai/codex.git", "codex"),
        ("https://github.com/openai/codex/", "codex"),
    ],
)
def test_returns_repository_name_when_github_url_is_provided(
    github_url: str,
    expected: str,
) -> None:
    # Arrange / Act
    repository_name = github_repository_name(github_url)

    # Assert
    assert repository_name == expected


def test_returns_velpos_roots_when_default_directories_are_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("HOME", str(tmp_path))

    # Act
    agent_root = default_agent_workspace_root()
    team_root = default_team_workspace_root()

    # Assert
    assert agent_root == tmp_path / "velpos" / "1" / "agents"
    assert team_root == tmp_path / "velpos" / "1" / "teams"

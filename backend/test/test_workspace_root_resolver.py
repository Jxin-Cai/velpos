from pathlib import Path

import pytest

from infr.config.app_config import app_config
from infr.workspace.workspace_root_resolver_impl import WorkspaceRootResolverImpl


def test_returns_user_scoped_roots_when_user_id_is_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setattr(app_config, "projects_root_dir", tmp_path / "velpos")
    resolver = WorkspaceRootResolverImpl()

    # Act
    user_root = resolver.user_root(42)
    agent_root = resolver.agent_root(42)
    team_root = resolver.team_root(42)

    # Assert
    assert user_root == tmp_path / "velpos" / "42"
    assert agent_root == user_root / "agents"
    assert team_root == user_root / "teams"


def test_rejects_user_root_when_user_id_is_not_positive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setattr(app_config, "projects_root_dir", tmp_path / "velpos")
    resolver = WorkspaceRootResolverImpl()

    # Act / Assert
    with pytest.raises(ValueError, match="positive integer"):
        resolver.user_root(0)

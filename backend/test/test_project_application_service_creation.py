from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from application.project.command.create_project_command import CreateProjectCommand
from application.project.project_application_service import ProjectApplicationService


def _service(project_repository: AsyncMock) -> ProjectApplicationService:
    return ProjectApplicationService(
        project_repository=project_repository,
        session_repository=AsyncMock(),
        session_service_factory=AsyncMock(),
        connection_manager=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_uses_agent_name_when_name_is_provided(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("HOME", str(tmp_path))
    repository = AsyncMock()
    service = _service(repository)
    command = CreateProjectCommand(name="Research Agent")

    # Act
    project = await service.create_project(command)

    # Assert
    assert project.name == "Research Agent"


@pytest.mark.asyncio
async def test_uses_real_directory_name_when_agent_name_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("HOME", str(tmp_path))
    repository = AsyncMock()
    service = _service(repository)
    command = CreateProjectCommand(name="")

    # Act
    project = await service.create_project(command)

    # Assert
    assert project.name == Path(project.dir_path).name
    assert Path(project.dir_path).parent == tmp_path / ".velpos" / "agents"


@pytest.mark.asyncio
async def test_uses_repository_name_when_github_agent_name_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("HOME", str(tmp_path))
    clone_process = SimpleNamespace(
        returncode=0,
        communicate=AsyncMock(return_value=(b"", b"")),
    )
    monkeypatch.setattr(
        "application.project.project_application_service.asyncio.create_subprocess_exec",
        AsyncMock(return_value=clone_process),
    )
    service = _service(AsyncMock())
    command = CreateProjectCommand(
        name="",
        github_url="https://github.com/openai/codex.git",
    )

    # Act
    project = await service.create_project(command)

    # Assert
    assert project.name == "codex"


@pytest.mark.asyncio
async def test_clones_repository_into_generated_agent_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv("HOME", str(tmp_path))
    clone_process = SimpleNamespace(
        returncode=0,
        communicate=AsyncMock(return_value=(b"", b"")),
    )
    create_subprocess = AsyncMock(return_value=clone_process)
    monkeypatch.setattr(
        "application.project.project_application_service.asyncio.create_subprocess_exec",
        create_subprocess,
    )
    service = _service(AsyncMock())
    github_url = "https://github.com/openai/codex.git"

    # Act
    project = await service.create_project(
        CreateProjectCommand(name="", github_url=github_url)
    )

    # Assert
    create_subprocess.assert_awaited_once_with(
        "git",
        "clone",
        github_url,
        ".",
        cwd=project.dir_path,
        stdout=-1,
        stderr=-1,
    )

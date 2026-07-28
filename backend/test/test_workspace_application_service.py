from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from application.project.workspace_application_service import WorkspaceApplicationService
from domain.shared.business_exception import BusinessException


def _service(project_dir: Path) -> WorkspaceApplicationService:
    repository = SimpleNamespace(
        find_by_id=AsyncMock(
            return_value=SimpleNamespace(
                id="project-1",
                name="Project",
                dir_path=str(project_dir),
            )
        )
    )
    return WorkspaceApplicationService(repository)


@pytest.mark.asyncio
async def test_hides_claude_instructions_when_workspace_files_are_listed(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("instructions", encoding="utf-8")
    (tmp_path / "README.md").write_text("readme", encoding="utf-8")
    service = _service(tmp_path)

    # Act
    files = await service.list_workspace_files("project-1")

    # Assert
    assert [file["path"] for file in files] == ["README.md"]


@pytest.mark.asyncio
async def test_lists_uploaded_file_when_workspace_files_are_listed(tmp_path: Path) -> None:
    # Arrange
    uploaded = tmp_path / ".upload-file" / "session-1" / "image.png"
    uploaded.parent.mkdir(parents=True)
    uploaded.write_bytes(b"image")
    service = _service(tmp_path)

    # Act
    files = await service.list_workspace_files("project-1")

    # Assert
    assert files[0]["path"] == ".upload-file/session-1/image.png"


@pytest.mark.asyncio
async def test_lists_accessible_files_when_workspace_directory_scan_is_interrupted(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "README.md").write_text("readme", encoding="utf-8")
    service = _service(tmp_path)

    def interrupted_walk(root, *, topdown, onerror, followlinks):
        onerror(InterruptedError(4, "Interrupted system call", str(tmp_path / "Library")))
        yield str(root), [], ["README.md"]

    # Act
    with patch(
        "application.project.workspace_application_service.os.walk",
        side_effect=interrupted_walk,
    ):
        files = await service.list_workspace_files("project-1")

    # Assert
    assert [file["path"] for file in files] == ["README.md"]


@pytest.mark.asyncio
async def test_rejects_claude_instruction_when_hidden_path_is_read(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "CLAUDE.md").write_text("instructions", encoding="utf-8")
    service = _service(tmp_path)

    # Act / Assert
    with pytest.raises(BusinessException, match="Workspace path is hidden"):
        await service.read_workspace_file("project-1", "CLAUDE.md")

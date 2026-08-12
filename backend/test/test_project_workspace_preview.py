from unittest.mock import AsyncMock

import pytest
from fastapi.responses import FileResponse

from ohs.http.project_router import preview_workspace_file


@pytest.mark.asyncio
async def test_returns_inline_file_when_workspace_file_is_previewed(tmp_path):
    # Arrange
    html_path = tmp_path / "index.html"
    html_path.write_text("<a href='next.html'>Next</a>", encoding="utf-8")
    service = AsyncMock()
    service.read_workspace_file_raw.return_value = html_path

    # Act
    response = await preview_workspace_file("project-1", "docs/index.html", service)

    # Assert
    assert isinstance(response, FileResponse)
    assert response.headers["content-disposition"] == "inline"


@pytest.mark.asyncio
async def test_applies_sandbox_when_html_workspace_file_is_previewed(tmp_path):
    # Arrange
    html_path = tmp_path / "index.html"
    html_path.write_text("<script>window.ready = true</script>", encoding="utf-8")
    service = AsyncMock()
    service.read_workspace_file_raw.return_value = html_path

    # Act
    response = await preview_workspace_file("project-1", "docs/index.html", service)

    # Assert
    assert response.headers["content-security-policy"].startswith("sandbox ")


@pytest.mark.asyncio
async def test_uses_requested_relative_path_when_workspace_file_is_previewed(tmp_path):
    # Arrange
    html_path = tmp_path / "next.html"
    html_path.write_text("Next", encoding="utf-8")
    service = AsyncMock()
    service.read_workspace_file_raw.return_value = html_path

    # Act
    await preview_workspace_file("project-1", "docs/next.html", service)

    # Assert
    service.read_workspace_file_raw.assert_awaited_once_with(
        "project-1",
        "docs/next.html",
    )

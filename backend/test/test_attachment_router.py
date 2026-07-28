from unittest.mock import AsyncMock

import pytest
from fastapi.responses import FileResponse

from domain.shared.business_exception import BusinessException
from ohs.http.attachment_router import preview_attachment


@pytest.mark.asyncio
async def test_returns_inline_image_when_attachment_is_previewable(tmp_path):
    # Arrange
    image_path = tmp_path / "example.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    service = AsyncMock()
    service.get_download_path.return_value = (
        str(image_path),
        "example.png",
        "image/png",
    )

    # Act
    response = await preview_attachment("attachment-1", service)

    # Assert
    assert isinstance(response, FileResponse)
    assert response.headers["content-disposition"] == "inline"


@pytest.mark.asyncio
async def test_rejects_inline_preview_when_attachment_is_not_an_image(tmp_path):
    # Arrange
    file_path = tmp_path / "example.pdf"
    file_path.write_bytes(b"%PDF")
    service = AsyncMock()
    service.get_download_path.return_value = (
        str(file_path),
        "example.pdf",
        "application/pdf",
    )

    # Act / Assert
    with pytest.raises(BusinessException) as error:
        await preview_attachment("attachment-1", service)
    assert error.value.code == "ATTACHMENT_PREVIEW_UNSUPPORTED"

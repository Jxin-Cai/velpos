from __future__ import annotations

from pathlib import Path

import pytest

from application.message.attachment_application_service import AttachmentApplicationService
from domain.message.model.attachment import Attachment, MAX_ATTACHMENT_BYTES, ensure_within_attachment_limit
from domain.shared.business_exception import BusinessException


def test_returns_project_relative_path_when_attachment_is_added_to_message(tmp_path: Path) -> None:
    # Arrange
    upload_path = tmp_path / ".upload-file" / "session-1" / "image.png"
    upload_path.parent.mkdir(parents=True)
    upload_path.write_bytes(b"image")
    attachment = Attachment.create(
        project_id="project-1",
        session_id="session-1",
        filename="image.png",
        mime_type="image/png",
        size_bytes=5,
        storage_path=str(upload_path),
        sha256="sha",
    )

    # Act
    message_ref = AttachmentApplicationService.to_workspace_message_ref(
        attachment,
        str(tmp_path),
    )

    # Assert
    assert message_ref["path"] == ".upload-file/session-1/image.png"


def test_returns_legacy_workspace_image_when_attachment_record_is_missing(tmp_path: Path) -> None:
    # Arrange
    image_path = tmp_path / ".uploads" / "by-session" / "session-1" / "image"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"image")

    # Act
    path, mime_type = AttachmentApplicationService.get_workspace_preview_path(
        str(tmp_path),
        ".uploads/by-session/session-1/image",
        "image/jpeg",
    )

    # Assert
    assert (path, mime_type) == (str(image_path), "image/jpeg")


def test_rejects_workspace_preview_when_path_escapes_session_directory(tmp_path: Path) -> None:
    # Arrange
    outside_path = tmp_path.parent / "outside.png"
    outside_path.write_bytes(b"image")

    # Act / Assert
    with pytest.raises(BusinessException) as error:
        AttachmentApplicationService.get_workspace_preview_path(
            str(tmp_path),
            "../outside.png",
            "image/png",
        )
    assert error.value.code == "INVALID_ATTACHMENT_PATH"


def test_rejects_size_when_payload_exceeds_attachment_limit():
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="10MB"):
        ensure_within_attachment_limit(MAX_ATTACHMENT_BYTES + 1)


def test_allows_size_when_payload_is_at_attachment_limit():
    # Arrange / Act / Assert
    ensure_within_attachment_limit(MAX_ATTACHMENT_BYTES)

from __future__ import annotations

from pathlib import Path

from infr.storage.attachment_storage_gateway import AttachmentStorageGateway


def test_stores_upload_under_session_directory_when_project_is_available(tmp_path: Path) -> None:
    # Arrange
    gateway = AttachmentStorageGateway()

    # Act
    stored_path, _ = gateway.save(
        str(tmp_path),
        "session-42",
        "demo image.png",
        b"image-content",
    )

    # Assert
    assert Path(stored_path).relative_to(tmp_path).as_posix() == (
        ".upload-file/session-42/demo-image.png"
    )


def test_stages_downloaded_media_inside_project_when_source_is_temporary(
    tmp_path: Path,
) -> None:
    # Arrange
    gateway = AttachmentStorageGateway()
    project_dir = tmp_path / "project"
    source = tmp_path / "lark-image.png"
    source.write_bytes(b"lark-image")

    # Act
    stored_path, _ = gateway.stage_file(
        str(project_dir),
        "session-42",
        "lark image.png",
        str(source),
    )

    # Assert
    assert Path(stored_path).relative_to(project_dir).as_posix() == (
        ".upload-file/session-42/lark-image.png"
    )


def test_adds_digest_suffix_when_session_upload_name_conflicts(tmp_path: Path) -> None:
    # Arrange
    gateway = AttachmentStorageGateway()
    gateway.save(str(tmp_path), "session-42", "report.md", b"first")

    # Act
    stored_path, _ = gateway.save(
        str(tmp_path),
        "session-42",
        "report.md",
        b"second",
    )

    # Assert
    assert Path(stored_path).relative_to(tmp_path).as_posix() == (
        ".upload-file/session-42/report-16367aacb6.md"
    )


def test_sanitizes_session_directory_when_session_id_contains_path_segments(
    tmp_path: Path,
) -> None:
    # Arrange
    gateway = AttachmentStorageGateway()

    # Act
    stored_path, _ = gateway.save(
        str(tmp_path),
        "../session-42",
        "report.md",
        b"content",
    )

    # Assert
    assert Path(stored_path).relative_to(tmp_path).as_posix() == (
        ".upload-file/session-42/report.md"
    )


def test_preserves_extension_when_filename_has_non_ascii_stem(
    tmp_path: Path,
) -> None:
    # Arrange
    gateway = AttachmentStorageGateway()

    # Act
    stored_path, _ = gateway.save(
        str(tmp_path),
        "session-42",
        "车.jpg",
        b"image",
    )

    # Assert
    assert Path(stored_path).name == "attachment.jpg"

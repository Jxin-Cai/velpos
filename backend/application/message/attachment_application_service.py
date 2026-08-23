from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
from typing import Any, Protocol

from domain.message.model.attachment import Attachment, ensure_within_attachment_limit
from domain.message.repository.attachment_repository import AttachmentRepository
from domain.project.repository.project_repository import ProjectRepository
from domain.shared.business_exception import BusinessException


class AttachmentStoragePort(Protocol):
    def save(
        self,
        project_dir: str,
        session_id: str,
        filename: str,
        data: bytes,
    ) -> tuple[str, str]:
        ...


class AttachmentApplicationService:

    def __init__(
        self,
        attachment_repository: AttachmentRepository,
        project_repository: ProjectRepository,
        storage_gateway: AttachmentStoragePort,
    ) -> None:
        self._attachment_repository = attachment_repository
        self._project_repository = project_repository
        self._storage_gateway = storage_gateway

    async def save_base64_attachment(
        self,
        project_id: str,
        session_id: str,
        project_dir: str,
        filename: str,
        mime_type: str,
        data_base64: str,
    ) -> Attachment:
        if not data_base64:
            raise BusinessException("Attachment data is required")
        try:
            data = base64.b64decode(data_base64, validate=True)
        except binascii.Error as exc:
            raise BusinessException("Invalid attachment data") from exc
        try:
            ensure_within_attachment_limit(len(data))
        except ValueError as exc:
            raise BusinessException(str(exc)) from exc
        if project_id and not project_dir:
            project = await self._project_repository.find_by_id(project_id)
            project_dir = project.dir_path if project else ""
        path, digest = self._storage_gateway.save(project_dir, session_id, filename, data)
        attachment = Attachment.create(
            project_id=project_id,
            session_id=session_id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(data),
            storage_path=path,
            sha256=digest,
        )
        await self._attachment_repository.save(attachment)
        return attachment

    @staticmethod
    def to_workspace_message_ref(attachment: Attachment, project_dir: str) -> dict[str, Any]:
        ref = attachment.to_message_ref()
        if not project_dir:
            return ref
        root = Path(project_dir).resolve()
        stored_path = Path(attachment.storage_path).resolve()
        if stored_path != root and root not in stored_path.parents:
            raise BusinessException("Attachment path is outside project workspace")
        ref["path"] = stored_path.relative_to(root).as_posix()
        return ref

    async def link_message(self, message_id: str, attachment_ids: list[str]) -> None:
        for attachment_id in attachment_ids:
            await self._attachment_repository.link_message(message_id, attachment_id)

    async def list_session_attachments(self, session_id: str) -> list[dict[str, Any]]:
        attachments = await self._attachment_repository.find_by_session_id(session_id)
        return [self.attachment_to_dict(item) for item in attachments]

    async def get_download_path(self, attachment_id: str) -> tuple[str, str, str]:
        attachment = await self._attachment_repository.find_by_id(attachment_id)
        if attachment is None:
            raise BusinessException("Attachment not found")
        if not os.path.isfile(attachment.storage_path):
            raise BusinessException("Attachment file not found")
        return attachment.storage_path, attachment.filename, attachment.mime_type

    @staticmethod
    def get_workspace_preview_path(
        project_dir: str,
        relative_path: str,
        mime_type: str,
    ) -> tuple[str, str]:
        root = Path(project_dir).expanduser().resolve()
        file_path = (root / relative_path).resolve()
        if file_path != root and root not in file_path.parents:
            raise BusinessException(
                "Attachment path is outside session workspace",
                "INVALID_ATTACHMENT_PATH",
            )
        if not mime_type.startswith("image/"):
            raise BusinessException(
                "Only image attachments support inline preview",
                "ATTACHMENT_PREVIEW_UNSUPPORTED",
            )
        if not file_path.is_file():
            raise BusinessException("Attachment file not found", "ATTACHMENT_FILE_NOT_FOUND")
        return str(file_path), mime_type

    @staticmethod
    def attachment_to_dict(attachment: Attachment) -> dict[str, Any]:
        return {
            "id": attachment.id,
            "project_id": attachment.project_id,
            "session_id": attachment.session_id,
            "filename": attachment.filename,
            "mime_type": attachment.mime_type,
            "size_bytes": attachment.size_bytes,
            "sha256": attachment.sha256,
            "created_time": attachment.created_time.isoformat(),
        }

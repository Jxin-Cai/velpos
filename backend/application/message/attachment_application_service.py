from __future__ import annotations

import base64
import binascii
import os
from typing import Any, Protocol

from domain.message.model.attachment import Attachment
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
        if len(data) > 25 * 1024 * 1024:
            raise BusinessException("Attachment exceeds 25MB limit")
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

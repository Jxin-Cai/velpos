from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.message.model.attachment import Attachment
from domain.message.repository.attachment_repository import AttachmentRepository
from infr.repository.attachment_model import AttachmentModel, MessageAttachmentModel


class AttachmentRepositoryImpl(AttachmentRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, attachment: Attachment) -> None:
        await self._session.merge(self._to_model(attachment))
        await self._session.flush()

    async def find_by_id(self, attachment_id: str) -> Attachment | None:
        result = await self._session.execute(
            select(AttachmentModel).where(AttachmentModel.id == attachment_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def find_by_session_id(self, session_id: str) -> list[Attachment]:
        result = await self._session.execute(
            select(AttachmentModel)
            .where(AttachmentModel.session_id == session_id)
            .order_by(AttachmentModel.created_time.desc())
        )
        return [self._to_domain(model) for model in result.scalars().all()]

    async def link_message(self, message_id: str, attachment_id: str) -> None:
        stmt = insert(MessageAttachmentModel).values(
            message_id=message_id,
            attachment_id=attachment_id,
        ).prefix_with("IGNORE")
        await self._session.execute(stmt)
        await self._session.flush()

    @staticmethod
    def _to_model(attachment: Attachment) -> AttachmentModel:
        return AttachmentModel(
            id=attachment.id,
            project_id=attachment.project_id,
            session_id=attachment.session_id,
            filename=attachment.filename,
            mime_type=attachment.mime_type,
            size_bytes=attachment.size_bytes,
            storage_path=attachment.storage_path,
            sha256=attachment.sha256,
            created_time=attachment.created_time,
        )

    @staticmethod
    def _to_domain(model: AttachmentModel) -> Attachment:
        return Attachment(
            id=model.id,
            project_id=model.project_id,
            session_id=model.session_id,
            filename=model.filename,
            mime_type=model.mime_type,
            size_bytes=model.size_bytes,
            storage_path=model.storage_path,
            sha256=model.sha256,
            created_time=model.created_time,
        )

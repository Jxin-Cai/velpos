from __future__ import annotations

from abc import ABC, abstractmethod

from domain.message.model.attachment import Attachment


class AttachmentRepository(ABC):

    @abstractmethod
    async def save(self, attachment: Attachment) -> None:
        raise NotImplementedError

    @abstractmethod
    async def find_by_id(self, attachment_id: str) -> Attachment | None:
        raise NotImplementedError

    @abstractmethod
    async def find_by_session_id(self, session_id: str) -> list[Attachment]:
        raise NotImplementedError

    @abstractmethod
    async def link_message(self, message_id: str, attachment_id: str) -> None:
        raise NotImplementedError

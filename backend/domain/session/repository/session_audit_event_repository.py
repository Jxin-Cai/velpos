from __future__ import annotations

from abc import ABC, abstractmethod

from domain.session.model.session_audit_event import SessionAuditEvent


class SessionAuditEventRepository(ABC):

    @abstractmethod
    async def save(self, event: SessionAuditEvent) -> None:
        ...

    @abstractmethod
    async def find_by_session_id(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[SessionAuditEvent]:
        ...

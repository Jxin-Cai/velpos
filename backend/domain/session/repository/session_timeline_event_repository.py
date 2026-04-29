from __future__ import annotations

from abc import ABC, abstractmethod

from domain.session.model.session_timeline_event import SessionTimelineEvent


class SessionTimelineEventRepository(ABC):

    @abstractmethod
    async def save(self, event: SessionTimelineEvent) -> None:
        ...

    @abstractmethod
    async def find_by_session_id(
        self,
        session_id: str,
        limit: int = 500,
        event_types: list[str] | None = None,
    ) -> list[SessionTimelineEvent]:
        ...

    @abstractmethod
    async def find_by_run_id(self, session_id: str, run_id: str) -> list[SessionTimelineEvent]:
        ...

    @abstractmethod
    async def next_seq(self, session_id: str, run_id: str) -> int:
        ...

    @abstractmethod
    async def commit(self) -> None:
        ...

    @abstractmethod
    async def rollback(self) -> None:
        ...

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.session.model.session_snapshot import SessionSnapshot


class SessionSnapshotRepository(ABC):

    @abstractmethod
    async def save(self, snapshot: SessionSnapshot) -> None:
        ...

    @abstractmethod
    async def find_by_session_id(self, session_id: str) -> list[SessionSnapshot]:
        ...

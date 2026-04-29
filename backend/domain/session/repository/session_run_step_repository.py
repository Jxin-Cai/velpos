from __future__ import annotations

from abc import ABC, abstractmethod

from domain.session.model.session_run_step import SessionRunStep


class SessionRunStepRepository(ABC):

    @abstractmethod
    async def save(self, step: SessionRunStep) -> None:
        ...

    @abstractmethod
    async def find_by_run_id(self, session_id: str, run_id: str) -> list[SessionRunStep]:
        ...

    @abstractmethod
    async def find_latest_run_id(self, session_id: str) -> str:
        ...

    @abstractmethod
    async def commit(self) -> None:
        ...

    @abstractmethod
    async def rollback(self) -> None:
        ...

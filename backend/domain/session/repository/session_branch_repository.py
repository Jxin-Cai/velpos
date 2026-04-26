from __future__ import annotations

from abc import ABC, abstractmethod

from domain.session.model.session_branch import SessionBranch


class SessionBranchRepository(ABC):

    @abstractmethod
    async def save(self, branch: SessionBranch) -> None:
        ...

    @abstractmethod
    async def find_by_source_session_id(self, session_id: str) -> list[SessionBranch]:
        ...

    @abstractmethod
    async def find_by_branch_session_id(self, session_id: str) -> SessionBranch | None:
        ...

    @abstractmethod
    async def find_by_root_session_id(self, session_id: str) -> list[SessionBranch]:
        ...

    @abstractmethod
    async def find_by_group_id(self, group_id: str) -> list[SessionBranch]:
        ...

    @abstractmethod
    async def remove_by_branch_session_id(self, session_id: str) -> bool:
        ...

    @abstractmethod
    async def remove_by_group_id(self, group_id: str) -> int:
        ...

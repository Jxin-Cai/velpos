from __future__ import annotations

from abc import ABC, abstractmethod

from domain.market.model.mcp_server_entry import McpServerEntry


class McpServerEntryRepository(ABC):

    @abstractmethod
    async def save(self, entry: McpServerEntry) -> McpServerEntry:
        ...

    @abstractmethod
    async def find_by_id(self, entry_id: str) -> McpServerEntry | None:
        ...

    @abstractmethod
    async def find_by_ids(self, entry_ids: list[str]) -> list[McpServerEntry]:
        ...

    @abstractmethod
    async def find_by_name(self, name: str) -> McpServerEntry | None:
        ...

    @abstractmethod
    async def search(
        self,
        keyword: str | None = None,
        category: str | None = None,
        only_active: bool = False,
    ) -> list[McpServerEntry]:
        ...

    @abstractmethod
    async def remove(self, entry_id: str) -> None:
        ...

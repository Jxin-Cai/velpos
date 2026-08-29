from __future__ import annotations

from abc import ABC, abstractmethod

from domain.market.model.skill_entry import SkillEntry


class SkillEntryRepository(ABC):

    @abstractmethod
    async def save(self, entry: SkillEntry) -> SkillEntry:
        ...

    @abstractmethod
    async def find_by_id(self, entry_id: str) -> SkillEntry | None:
        ...

    @abstractmethod
    async def find_by_ids(self, entry_ids: list[str]) -> list[SkillEntry]:
        ...

    @abstractmethod
    async def find_by_name(self, name: str) -> SkillEntry | None:
        ...

    @abstractmethod
    async def find_by_source_ref(self, source_ref: str) -> SkillEntry | None:
        ...

    @abstractmethod
    async def search(
        self,
        keyword: str | None = None,
        category: str | None = None,
        only_active: bool = False,
        source: str | None = None,
    ) -> list[SkillEntry]:
        ...

    @abstractmethod
    async def remove(self, entry_id: str) -> None:
        ...

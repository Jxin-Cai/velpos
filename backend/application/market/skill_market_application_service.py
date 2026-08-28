from __future__ import annotations

import uuid

from dataclasses import dataclass, field

from domain.market.model.market_categories import SkillCategory
from domain.market.model.skill_entry import SkillEntry
from domain.market.repository.skill_entry_repository import SkillEntryRepository
from domain.shared.business_exception import BusinessException


@dataclass(frozen=True)
class CreateSkillEntryCommand:
    name: str
    display_name: str
    description: str
    category: SkillCategory
    content: str
    created_by: int
    tags: tuple[str, ...] = field(default_factory=tuple)
    repo_url: str = ""
    author: str = ""
    version: str = ""
    logo_emoji: str = "🎯"


@dataclass(frozen=True)
class UpdateSkillEntryCommand:
    entry_id: str
    name: str
    display_name: str
    description: str
    category: SkillCategory
    content: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    repo_url: str = ""
    author: str = ""
    version: str = ""
    logo_emoji: str = "🎯"
    is_active: bool = True


class SkillMarketApplicationService:

    def __init__(self, repository: SkillEntryRepository) -> None:
        self._repository = repository

    async def create_entry(self, command: CreateSkillEntryCommand) -> SkillEntry:
        duplicated = await self._repository.find_by_name(command.name)
        if duplicated is not None:
            raise BusinessException(f"Skill entry already exists: {command.name}")

        entry = SkillEntry.create(
            id=str(uuid.uuid4()),
            name=command.name,
            display_name=command.display_name,
            description=command.description,
            category=command.category,
            tags=command.tags,
            content=command.content,
            created_by=command.created_by,
            repo_url=command.repo_url,
            author=command.author,
            version=command.version,
            logo_emoji=command.logo_emoji,
        )
        return await self._repository.save(entry)

    async def update_entry(self, command: UpdateSkillEntryCommand) -> SkillEntry:
        entry = await self._repository.find_by_id(command.entry_id)
        if entry is None:
            raise BusinessException(f"Skill entry not found: {command.entry_id}")

        duplicated = await self._repository.find_by_name(command.name)
        if duplicated is not None and duplicated.id != entry.id:
            raise BusinessException(f"Skill entry already exists: {command.name}")

        entry.update(
            name=command.name,
            display_name=command.display_name,
            description=command.description,
            category=command.category,
            tags=command.tags,
            content=command.content,
            repo_url=command.repo_url,
            author=command.author,
            version=command.version,
            logo_emoji=command.logo_emoji,
        )
        if command.is_active:
            entry.activate()
        else:
            entry.deactivate()
        return await self._repository.save(entry)

    async def delete_entry(self, entry_id: str) -> None:
        entry = await self._repository.find_by_id(entry_id)
        if entry is None:
            raise BusinessException(f"Skill entry not found: {entry_id}")
        await self._repository.remove(entry_id)

    async def search_entries(
        self,
        keyword: str | None = None,
        category: str | None = None,
        only_active: bool = False,
    ) -> list[SkillEntry]:
        return await self._repository.search(
            keyword=keyword,
            category=category,
            only_active=only_active,
        )

    async def get_entry(self, entry_id: str) -> SkillEntry:
        entry = await self._repository.find_by_id(entry_id)
        if entry is None:
            raise BusinessException(f"Skill entry not found: {entry_id}")
        return entry

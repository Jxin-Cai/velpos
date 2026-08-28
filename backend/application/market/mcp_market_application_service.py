from __future__ import annotations

import uuid

from dataclasses import dataclass, field

from domain.market.model.market_categories import McpCategory, McpTransport
from domain.market.model.mcp_server_entry import McpServerEntry
from domain.market.repository.mcp_server_entry_repository import McpServerEntryRepository
from domain.shared.business_exception import BusinessException


@dataclass(frozen=True)
class CreateMcpServerEntryCommand:
    name: str
    display_name: str
    description: str
    category: McpCategory
    transport: McpTransport
    server_config: dict
    created_by: int
    tags: tuple[str, ...] = field(default_factory=tuple)
    repo_url: str = ""
    homepage_url: str = ""
    author: str = ""
    version: str = ""
    logo_emoji: str = "🔌"


@dataclass(frozen=True)
class UpdateMcpServerEntryCommand:
    entry_id: str
    name: str
    display_name: str
    description: str
    category: McpCategory
    transport: McpTransport
    server_config: dict
    tags: tuple[str, ...] = field(default_factory=tuple)
    repo_url: str = ""
    homepage_url: str = ""
    author: str = ""
    version: str = ""
    logo_emoji: str = "🔌"
    is_active: bool = True


class McpMarketApplicationService:

    def __init__(self, repository: McpServerEntryRepository) -> None:
        self._repository = repository

    async def create_entry(self, command: CreateMcpServerEntryCommand) -> McpServerEntry:
        duplicated = await self._repository.find_by_name(command.name)
        if duplicated is not None:
            raise BusinessException(f"MCP server entry already exists: {command.name}")

        entry = McpServerEntry.create(
            id=str(uuid.uuid4()),
            name=command.name,
            display_name=command.display_name,
            description=command.description,
            category=command.category,
            tags=command.tags,
            transport=command.transport,
            server_config=command.server_config,
            created_by=command.created_by,
            repo_url=command.repo_url,
            homepage_url=command.homepage_url,
            author=command.author,
            version=command.version,
            logo_emoji=command.logo_emoji,
        )
        return await self._repository.save(entry)

    async def update_entry(self, command: UpdateMcpServerEntryCommand) -> McpServerEntry:
        entry = await self._repository.find_by_id(command.entry_id)
        if entry is None:
            raise BusinessException(f"MCP server entry not found: {command.entry_id}")

        duplicated = await self._repository.find_by_name(command.name)
        if duplicated is not None and duplicated.id != entry.id:
            raise BusinessException(f"MCP server entry already exists: {command.name}")

        entry.update(
            name=command.name,
            display_name=command.display_name,
            description=command.description,
            category=command.category,
            tags=command.tags,
            transport=command.transport,
            server_config=command.server_config,
            repo_url=command.repo_url,
            homepage_url=command.homepage_url,
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
            raise BusinessException(f"MCP server entry not found: {entry_id}")
        await self._repository.remove(entry_id)

    async def search_entries(
        self,
        keyword: str | None = None,
        category: str | None = None,
        only_active: bool = False,
    ) -> list[McpServerEntry]:
        return await self._repository.search(
            keyword=keyword,
            category=category,
            only_active=only_active,
        )

    async def get_entry(self, entry_id: str) -> McpServerEntry:
        entry = await self._repository.find_by_id(entry_id)
        if entry is None:
            raise BusinessException(f"MCP server entry not found: {entry_id}")
        return entry

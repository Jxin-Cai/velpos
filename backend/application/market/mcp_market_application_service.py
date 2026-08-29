from __future__ import annotations

import re
import uuid

from dataclasses import dataclass, field

from domain.market.acl.marketplace_catalog import McpMarketplaceCatalog, RemoteMcpServerPage
from domain.market.model.market_categories import (
    EntrySource,
    MarketplaceSort,
    McpCategory,
    McpTransport,
)
from domain.market.model.mcp_server_entry import McpServerEntry
from domain.market.repository.mcp_server_entry_repository import McpServerEntryRepository
from domain.shared.business_exception import BusinessException

_MAX_NAME_SUFFIX = 9


def slugify_entry_name(raw: str) -> str:
    """Turn an upstream marketplace ref (e.g. 'io.github.owner/repo') into a valid local name."""
    candidate = raw.rsplit("/", 1)[-1].lower()
    candidate = re.sub(r"[^a-z0-9._-]+", "-", candidate).strip("._-")
    return candidate or "entry"


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


@dataclass(frozen=True)
class ImportMcpServerEntryCommand:
    ref: str
    created_by: int


@dataclass(frozen=True)
class McpMarketplaceView:
    """A marketplace page plus the upstream refs that were already imported locally."""

    page: RemoteMcpServerPage
    imported_refs: frozenset[str]


class McpMarketApplicationService:

    def __init__(
        self,
        repository: McpServerEntryRepository,
        marketplace_catalog: McpMarketplaceCatalog | None = None,
    ) -> None:
        self._repository = repository
        self._marketplace_catalog = marketplace_catalog

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
        source: str | None = None,
    ) -> list[McpServerEntry]:
        return await self._repository.search(
            keyword=keyword,
            category=category,
            only_active=only_active,
            source=source,
        )

    async def browse_marketplace(
        self,
        keyword: str | None = None,
        page: int = 1,
        limit: int = 30,
        sort: MarketplaceSort = MarketplaceSort.STARS,
    ) -> McpMarketplaceView:
        catalog = self._require_catalog()
        remote_page = await catalog.search(keyword=keyword, page=page, limit=limit, sort=sort)
        imported = await self._repository.search(source=EntrySource.MARKETPLACE.value)
        return McpMarketplaceView(
            page=remote_page,
            imported_refs=frozenset(entry.source_ref for entry in imported if entry.source_ref),
        )

    async def import_from_marketplace(self, command: ImportMcpServerEntryCommand) -> McpServerEntry:
        catalog = self._require_catalog()
        existing = await self._repository.find_by_source_ref(command.ref)
        if existing is not None:
            raise BusinessException(f"Marketplace entry already imported: {existing.display_name}")

        remote = await catalog.get_server(command.ref)
        if remote is None:
            raise BusinessException(f"Marketplace entry not found: {command.ref}")

        try:
            category = McpCategory(remote.category)
        except ValueError:
            category = McpCategory.OTHER
        entry = McpServerEntry.create(
            id=str(uuid.uuid4()),
            name=await self._allocate_name(slugify_entry_name(remote.name)),
            display_name=remote.display_name,
            description=remote.description,
            category=category,
            tags=(),
            transport=remote.transport,
            server_config=remote.server_config,
            created_by=command.created_by,
            repo_url=remote.repo_url,
            homepage_url=remote.homepage_url,
            author=remote.author,
            version=remote.version,
            source=EntrySource.MARKETPLACE,
            source_ref=remote.ref,
        )
        return await self._repository.save(entry)

    async def _allocate_name(self, base_name: str) -> str:
        if await self._repository.find_by_name(base_name) is None:
            return base_name
        for suffix in range(2, _MAX_NAME_SUFFIX + 1):
            candidate = f"{base_name}-{suffix}"
            if await self._repository.find_by_name(candidate) is None:
                return candidate
        raise BusinessException(f"Too many entries named like: {base_name}")

    def _require_catalog(self) -> McpMarketplaceCatalog:
        if self._marketplace_catalog is None:
            raise BusinessException("MCP marketplace is not configured")
        return self._marketplace_catalog

    async def get_entry(self, entry_id: str) -> McpServerEntry:
        entry = await self._repository.find_by_id(entry_id)
        if entry is None:
            raise BusinessException(f"MCP server entry not found: {entry_id}")
        return entry

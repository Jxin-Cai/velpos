from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.market.model.market_categories import EntrySource, McpCategory, McpTransport
from domain.market.model.mcp_server_entry import McpServerEntry
from domain.market.repository.mcp_server_entry_repository import McpServerEntryRepository
from domain.shared.business_exception import BusinessException
from infr.repository.mcp_server_entry_model import McpServerEntryModel
from infr.repository.sql_like import LIKE_ESCAPE_CHAR, escape_like


class McpServerEntryRepositoryImpl(McpServerEntryRepository):

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session

    async def save(self, entry: McpServerEntry) -> McpServerEntry:
        existing = await self._db.get(McpServerEntryModel, entry.id)
        if existing is None:
            self._db.add(self._to_model(entry))
        else:
            existing.name = entry.name
            existing.display_name = entry.display_name
            existing.description = entry.description
            existing.category = entry.category.value
            existing.tags = list(entry.tags)
            existing.transport = entry.transport.value
            existing.server_config = entry.server_config
            existing.repo_url = entry.repo_url
            existing.homepage_url = entry.homepage_url
            existing.author = entry.author
            existing.version = entry.version
            existing.logo_emoji = entry.logo_emoji
            existing.source = entry.source.value
            existing.source_ref = entry.source_ref
            existing.updated_at = entry.updated_at
            existing.is_active = entry.is_active
        try:
            await self._db.flush()
        except IntegrityError as exc:
            raise BusinessException(
                f"MCP server entry name already exists: {entry.name}"
            ) from exc
        return entry

    async def find_by_id(self, entry_id: str) -> McpServerEntry | None:
        model = await self._db.get(McpServerEntryModel, entry_id)
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_ids(self, entry_ids: list[str]) -> list[McpServerEntry]:
        if not entry_ids:
            return []
        stmt = select(McpServerEntryModel).where(McpServerEntryModel.id.in_(entry_ids))
        result = await self._db.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_by_name(self, name: str) -> McpServerEntry | None:
        stmt = select(McpServerEntryModel).where(McpServerEntryModel.name == name)
        result = await self._db.execute(stmt)
        model = result.scalars().first()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_source_ref(self, source_ref: str) -> McpServerEntry | None:
        stmt = select(McpServerEntryModel).where(McpServerEntryModel.source_ref == source_ref)
        result = await self._db.execute(stmt)
        model = result.scalars().first()
        if model is None:
            return None
        return self._to_domain(model)

    async def search(
        self,
        keyword: str | None = None,
        category: str | None = None,
        only_active: bool = False,
        source: str | None = None,
    ) -> list[McpServerEntry]:
        stmt = select(McpServerEntryModel)
        if keyword:
            pattern = f"%{escape_like(keyword)}%"
            stmt = stmt.where(
                or_(
                    McpServerEntryModel.name.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
                    McpServerEntryModel.display_name.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
                    McpServerEntryModel.description.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
                    McpServerEntryModel.author.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
                )
            )
        if category:
            stmt = stmt.where(McpServerEntryModel.category == category)
        if only_active:
            stmt = stmt.where(McpServerEntryModel.is_active == True)  # noqa: E712
        if source:
            stmt = stmt.where(McpServerEntryModel.source == source)
        stmt = stmt.order_by(McpServerEntryModel.created_at.desc())
        result = await self._db.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def remove(self, entry_id: str) -> None:
        stmt = delete(McpServerEntryModel).where(McpServerEntryModel.id == entry_id)
        await self._db.execute(stmt)
        await self._db.flush()

    @staticmethod
    def _to_model(entry: McpServerEntry) -> McpServerEntryModel:
        return McpServerEntryModel(
            id=entry.id,
            name=entry.name,
            display_name=entry.display_name,
            description=entry.description,
            category=entry.category.value,
            tags=list(entry.tags),
            transport=entry.transport.value,
            server_config=entry.server_config,
            repo_url=entry.repo_url,
            homepage_url=entry.homepage_url,
            author=entry.author,
            version=entry.version,
            logo_emoji=entry.logo_emoji,
            source=entry.source.value,
            source_ref=entry.source_ref,
            created_by=entry.created_by,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
            is_active=entry.is_active,
        )

    @staticmethod
    def _to_domain(model: McpServerEntryModel) -> McpServerEntry:
        return McpServerEntry.reconstitute(
            id=model.id,
            name=model.name,
            display_name=model.display_name,
            description=model.description,
            category=McpCategory(model.category),
            tags=tuple(model.tags or []),
            transport=McpTransport(model.transport),
            server_config=model.server_config or {},
            repo_url=model.repo_url,
            homepage_url=model.homepage_url,
            author=model.author,
            version=model.version,
            logo_emoji=model.logo_emoji,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            is_active=model.is_active,
            source=EntrySource(model.source or EntrySource.CUSTOM.value),
            source_ref=model.source_ref or "",
        )

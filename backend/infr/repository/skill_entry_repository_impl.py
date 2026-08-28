from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.market.model.market_categories import SkillCategory
from domain.market.model.skill_entry import SkillEntry
from domain.market.repository.skill_entry_repository import SkillEntryRepository
from domain.shared.business_exception import BusinessException
from infr.repository.skill_entry_model import SkillEntryModel
from infr.repository.sql_like import LIKE_ESCAPE_CHAR, escape_like


class SkillEntryRepositoryImpl(SkillEntryRepository):

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session

    async def save(self, entry: SkillEntry) -> SkillEntry:
        existing = await self._db.get(SkillEntryModel, entry.id)
        if existing is None:
            self._db.add(self._to_model(entry))
        else:
            existing.name = entry.name
            existing.display_name = entry.display_name
            existing.description = entry.description
            existing.category = entry.category.value
            existing.tags = list(entry.tags)
            existing.content = entry.content
            existing.repo_url = entry.repo_url
            existing.author = entry.author
            existing.version = entry.version
            existing.logo_emoji = entry.logo_emoji
            existing.updated_at = entry.updated_at
            existing.is_active = entry.is_active
        try:
            await self._db.flush()
        except IntegrityError as exc:
            raise BusinessException(
                f"Skill entry name already exists: {entry.name}"
            ) from exc
        return entry

    async def find_by_id(self, entry_id: str) -> SkillEntry | None:
        model = await self._db.get(SkillEntryModel, entry_id)
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_ids(self, entry_ids: list[str]) -> list[SkillEntry]:
        if not entry_ids:
            return []
        stmt = select(SkillEntryModel).where(SkillEntryModel.id.in_(entry_ids))
        result = await self._db.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_by_name(self, name: str) -> SkillEntry | None:
        stmt = select(SkillEntryModel).where(SkillEntryModel.name == name)
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
    ) -> list[SkillEntry]:
        stmt = select(SkillEntryModel)
        if keyword:
            pattern = f"%{escape_like(keyword)}%"
            stmt = stmt.where(
                or_(
                    SkillEntryModel.name.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
                    SkillEntryModel.display_name.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
                    SkillEntryModel.description.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
                    SkillEntryModel.author.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
                )
            )
        if category:
            stmt = stmt.where(SkillEntryModel.category == category)
        if only_active:
            stmt = stmt.where(SkillEntryModel.is_active == True)  # noqa: E712
        stmt = stmt.order_by(SkillEntryModel.created_at.desc())
        result = await self._db.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def remove(self, entry_id: str) -> None:
        stmt = delete(SkillEntryModel).where(SkillEntryModel.id == entry_id)
        await self._db.execute(stmt)
        await self._db.flush()

    @staticmethod
    def _to_model(entry: SkillEntry) -> SkillEntryModel:
        return SkillEntryModel(
            id=entry.id,
            name=entry.name,
            display_name=entry.display_name,
            description=entry.description,
            category=entry.category.value,
            tags=list(entry.tags),
            content=entry.content,
            repo_url=entry.repo_url,
            author=entry.author,
            version=entry.version,
            logo_emoji=entry.logo_emoji,
            created_by=entry.created_by,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
            is_active=entry.is_active,
        )

    @staticmethod
    def _to_domain(model: SkillEntryModel) -> SkillEntry:
        return SkillEntry.reconstitute(
            id=model.id,
            name=model.name,
            display_name=model.display_name,
            description=model.description,
            category=SkillCategory(model.category),
            tags=tuple(model.tags or []),
            content=model.content,
            repo_url=model.repo_url,
            author=model.author,
            version=model.version,
            logo_emoji=model.logo_emoji,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            is_active=model.is_active,
        )

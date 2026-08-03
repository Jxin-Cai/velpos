from __future__ import annotations

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from domain.agent.model.agent_template import AgentTemplate
from domain.agent.repository.agent_template_repository import AgentTemplateRepository
from infr.repository.agent_template_model import AgentTemplateModel


class AgentTemplateRepositoryImpl(AgentTemplateRepository):

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session

    async def save(self, template: AgentTemplate) -> AgentTemplate:
        existing = await self._db.get(AgentTemplateModel, template.id)
        if existing is None:
            model = AgentTemplateModel(
                id=template.id,
                name_en=template.name_en,
                name_zh=template.name_zh,
                description_en=template.description_en,
                description_zh=template.description_zh,
                category=template.category,
                emoji=template.emoji,
                color=template.color,
                prompt_en=template.prompt_en,
                prompt_zh=template.prompt_zh,
                plugins_config=template.plugins_config,
                created_by=template.created_by,
                created_at=template.created_at,
                updated_at=template.updated_at,
                is_active=template.is_active,
            )
            self._db.add(model)
        else:
            existing.name_en = template.name_en
            existing.name_zh = template.name_zh
            existing.description_en = template.description_en
            existing.description_zh = template.description_zh
            existing.category = template.category
            existing.emoji = template.emoji
            existing.color = template.color
            existing.prompt_en = template.prompt_en
            existing.prompt_zh = template.prompt_zh
            existing.plugins_config = template.plugins_config
            existing.updated_at = template.updated_at
            existing.is_active = template.is_active
        await self._db.flush()
        return template

    async def find_by_id(self, template_id: str) -> AgentTemplate | None:
        model = await self._db.get(AgentTemplateModel, template_id)
        if model is None:
            return None
        return self._to_domain(model)

    async def find_all(self) -> list[AgentTemplate]:
        stmt = select(AgentTemplateModel).order_by(AgentTemplateModel.created_at.desc())
        result = await self._db.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_all_active(self) -> list[AgentTemplate]:
        stmt = (
            select(AgentTemplateModel)
            .where(AgentTemplateModel.is_active == True)  # noqa: E712
            .order_by(AgentTemplateModel.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def remove(self, template_id: str) -> None:
        stmt = delete(AgentTemplateModel).where(AgentTemplateModel.id == template_id)
        await self._db.execute(stmt)
        await self._db.flush()

    @staticmethod
    def _to_domain(model: AgentTemplateModel) -> AgentTemplate:
        return AgentTemplate.reconstitute(
            id=model.id,
            name_en=model.name_en,
            name_zh=model.name_zh,
            description_en=model.description_en,
            description_zh=model.description_zh,
            category=model.category,
            emoji=model.emoji,
            color=model.color,
            prompt_en=model.prompt_en,
            prompt_zh=model.prompt_zh,
            plugins_config=model.plugins_config,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            is_active=model.is_active,
        )

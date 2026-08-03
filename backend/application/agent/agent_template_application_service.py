from __future__ import annotations

import uuid

from dataclasses import dataclass

from domain.agent.model.agent_template import AgentTemplate
from domain.agent.repository.agent_template_repository import AgentTemplateRepository
from domain.shared.business_exception import BusinessException


@dataclass(frozen=True)
class CreateAgentTemplateCommand:
    name_en: str
    name_zh: str
    description_en: str
    description_zh: str
    category: str
    emoji: str
    color: str
    prompt_en: str
    prompt_zh: str
    created_by: int
    plugins_config: dict | None = None


@dataclass(frozen=True)
class UpdateAgentTemplateCommand:
    template_id: str
    name_en: str
    name_zh: str
    description_en: str
    description_zh: str
    category: str
    emoji: str
    color: str
    prompt_en: str
    prompt_zh: str
    plugins_config: dict | None = None


class AgentTemplateApplicationService:

    def __init__(self, repository: AgentTemplateRepository) -> None:
        self._repository = repository

    async def create_template(self, command: CreateAgentTemplateCommand) -> AgentTemplate:
        template = AgentTemplate.create(
            id=str(uuid.uuid4()),
            name_en=command.name_en,
            name_zh=command.name_zh,
            description_en=command.description_en,
            description_zh=command.description_zh,
            category=command.category,
            emoji=command.emoji,
            color=command.color,
            prompt_en=command.prompt_en,
            prompt_zh=command.prompt_zh,
            created_by=command.created_by,
            plugins_config=command.plugins_config,
        )
        return await self._repository.save(template)

    async def update_template(self, command: UpdateAgentTemplateCommand) -> AgentTemplate:
        template = await self._repository.find_by_id(command.template_id)
        if template is None:
            raise BusinessException(f"Agent template not found: {command.template_id}")

        template.update(
            name_en=command.name_en,
            name_zh=command.name_zh,
            description_en=command.description_en,
            description_zh=command.description_zh,
            category=command.category,
            emoji=command.emoji,
            color=command.color,
            prompt_en=command.prompt_en,
            prompt_zh=command.prompt_zh,
            plugins_config=command.plugins_config,
        )
        return await self._repository.save(template)

    async def delete_template(self, template_id: str) -> None:
        template = await self._repository.find_by_id(template_id)
        if template is None:
            raise BusinessException(f"Agent template not found: {template_id}")
        await self._repository.remove(template_id)

    async def list_all_templates(self) -> list[AgentTemplate]:
        return await self._repository.find_all()

    async def list_active_templates(self) -> list[AgentTemplate]:
        return await self._repository.find_all_active()

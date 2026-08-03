from __future__ import annotations

from abc import ABC, abstractmethod

from domain.agent.model.agent_template import AgentTemplate


class AgentTemplateRepository(ABC):

    @abstractmethod
    async def save(self, template: AgentTemplate) -> AgentTemplate:
        ...

    @abstractmethod
    async def find_by_id(self, template_id: str) -> AgentTemplate | None:
        ...

    @abstractmethod
    async def find_all(self) -> list[AgentTemplate]:
        ...

    @abstractmethod
    async def find_all_active(self) -> list[AgentTemplate]:
        ...

    @abstractmethod
    async def remove(self, template_id: str) -> None:
        ...

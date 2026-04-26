from __future__ import annotations

from abc import ABC, abstractmethod

from domain.command.model.project_command_policy import ProjectCommandPolicy


class ProjectCommandPolicyRepository(ABC):

    @abstractmethod
    async def save(self, policy: ProjectCommandPolicy) -> None:
        ...

    @abstractmethod
    async def find_by_project_id(self, project_id: str) -> list[ProjectCommandPolicy]:
        ...

    @abstractmethod
    async def find_by_project_and_command(
        self,
        project_id: str,
        command_name: str,
        command_type: str,
    ) -> ProjectCommandPolicy | None:
        ...

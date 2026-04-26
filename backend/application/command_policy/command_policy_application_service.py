from __future__ import annotations

from pathlib import Path
from typing import Any

from domain.command.model.project_command_policy import ProjectCommandPolicy
from domain.command.repository.project_command_policy_repository import ProjectCommandPolicyRepository
from domain.project.model.project import Project
from domain.project.repository.project_repository import ProjectRepository
from domain.shared.business_exception import BusinessException


class CommandPolicyApplicationService:

    def __init__(
        self,
        policy_repository: ProjectCommandPolicyRepository,
        project_repository: ProjectRepository,
    ) -> None:
        self._policy_repository = policy_repository
        self._project_repository = project_repository

    async def list_policies(
        self,
        project_id: str = "",
        project_dir: str = "",
    ) -> list[ProjectCommandPolicy]:
        project = await self._resolve_project(project_id, project_dir)
        return await self._policy_repository.find_by_project_id(project.id)

    async def save_policy(
        self,
        project_id: str = "",
        project_dir: str = "",
        command_name: str = "",
        command_type: str = "unknown",
        enabled: bool = True,
        visible: bool = True,
        default_args: dict[str, Any] | None = None,
    ) -> ProjectCommandPolicy:
        if not command_name.strip():
            raise BusinessException("Command name is required")
        project = await self._resolve_project(project_id, project_dir)
        policy = await self._policy_repository.find_by_project_and_command(
            project.id,
            command_name.strip(),
            command_type or "unknown",
        )
        if policy is None:
            policy = ProjectCommandPolicy.create(
                project_id=project.id,
                command_name=command_name.strip(),
                command_type=command_type,
                enabled=enabled,
                visible=visible,
                default_args=default_args,
            )
        else:
            policy.update(
                enabled=enabled,
                visible=visible,
                default_args=default_args,
                command_type=command_type,
            )
        await self._policy_repository.save(policy)
        return policy

    async def filter_commands(
        self,
        commands: list[dict[str, Any]],
        project_dir: str,
    ) -> list[dict[str, Any]]:
        project = await self._resolve_project("", project_dir)
        policies = await self._policy_repository.find_by_project_id(project.id)
        policy_map = {
            (policy.command_name, policy.command_type): policy
            for policy in policies
        }
        result: list[dict[str, Any]] = []
        for command in commands:
            name = command.get("name", "")
            command_type = command.get("type", "unknown")
            policy = policy_map.get((name, command_type)) or policy_map.get((name, "unknown"))
            if policy is not None:
                command = {
                    **command,
                    "policy": self.policy_to_dict(policy),
                    "enabled": policy.enabled,
                    "visible": policy.visible,
                    "default_args": policy.default_args,
                }
                if not policy.enabled or not policy.visible:
                    continue
            else:
                command = {
                    **command,
                    "enabled": True,
                    "visible": True,
                    "default_args": {},
                }
            result.append(command)
        return result

    async def _resolve_project(self, project_id: str = "", project_dir: str = "") -> Project:
        if project_id:
            project = await self._project_repository.find_by_id(project_id)
            if project is None:
                raise BusinessException("Project not found")
            return project
        if not project_dir:
            raise BusinessException("Project id or directory is required")
        project_path = Path(project_dir).expanduser().resolve()
        if not project_path.is_dir():
            raise BusinessException("Project directory not found")
        project = await self._project_repository.find_by_dir_path(str(project_path))
        if project is None:
            project = Project.create(project_path.name, str(project_path))
            await self._project_repository.save(project)
        return project

    @staticmethod
    def policy_to_dict(policy: ProjectCommandPolicy) -> dict[str, Any]:
        return {
            "id": policy.id,
            "project_id": policy.project_id,
            "command_name": policy.command_name,
            "command_type": policy.command_type,
            "enabled": policy.enabled,
            "visible": policy.visible,
            "default_args": policy.default_args,
            "updated_time": policy.updated_time.isoformat(),
        }

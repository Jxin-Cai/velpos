from __future__ import annotations

from typing import Any

from application.shared.project_resolver import resolve_project
from domain.command.model.project_command_policy import ProjectCommandPolicy
from domain.command.repository.project_command_policy_repository import ProjectCommandPolicyRepository
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
        project = await resolve_project(self._project_repository, project_id, project_dir)
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
        project = await resolve_project(self._project_repository, project_id, project_dir)
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
        project = await resolve_project(self._project_repository, "", project_dir)
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

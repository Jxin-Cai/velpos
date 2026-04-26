from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.command.model.project_command_policy import ProjectCommandPolicy
from domain.command.repository.project_command_policy_repository import ProjectCommandPolicyRepository
from infr.repository.project_command_policy_model import ProjectCommandPolicyModel


class ProjectCommandPolicyRepositoryImpl(ProjectCommandPolicyRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, policy: ProjectCommandPolicy) -> None:
        await self._session.merge(self._to_model(policy))
        await self._session.flush()

    async def find_by_project_id(self, project_id: str) -> list[ProjectCommandPolicy]:
        stmt = (
            select(ProjectCommandPolicyModel)
            .where(ProjectCommandPolicyModel.project_id == project_id)
            .order_by(ProjectCommandPolicyModel.command_name.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_by_project_and_command(
        self,
        project_id: str,
        command_name: str,
        command_type: str,
    ) -> ProjectCommandPolicy | None:
        stmt = select(ProjectCommandPolicyModel).where(
            ProjectCommandPolicyModel.project_id == project_id,
            ProjectCommandPolicyModel.command_name == command_name,
            ProjectCommandPolicyModel.command_type == command_type,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    @staticmethod
    def _to_model(policy: ProjectCommandPolicy) -> ProjectCommandPolicyModel:
        return ProjectCommandPolicyModel(
            id=policy.id,
            project_id=policy.project_id,
            command_name=policy.command_name,
            command_type=policy.command_type,
            enabled=1 if policy.enabled else 0,
            visible=1 if policy.visible else 0,
            default_args_json=policy.default_args,
            updated_time=policy.updated_time,
        )

    @staticmethod
    def _to_domain(model: ProjectCommandPolicyModel) -> ProjectCommandPolicy:
        return ProjectCommandPolicy(
            id=model.id,
            project_id=model.project_id,
            command_name=model.command_name,
            command_type=model.command_type,
            enabled=model.enabled == 1,
            visible=model.visible == 1,
            default_args=model.default_args_dict,
            updated_time=model.updated_time,
        )

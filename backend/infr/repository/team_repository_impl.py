from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from domain.team.model.agent_slot import AgentSlot
from domain.team.model.team import Team
from domain.team.repository.team_repository import TeamRepository
from infr.repository.repo_helpers import remove_by_pk
from infr.repository.team_model import AgentSlotModel, TeamModel


class TeamRepositoryImpl(TeamRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, team: Team) -> None:
        await self._session.merge(self._to_model(team))
        await self._session.flush()

    async def find_by_id(self, team_id: str) -> Team | None:
        stmt = (
            select(TeamModel)
            .options(selectinload(TeamModel.agent_slots))
            .where(TeamModel.id == team_id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def find_by_project_id(self, project_id: str) -> Team | None:
        stmt = (
            select(TeamModel)
            .options(selectinload(TeamModel.agent_slots))
            .where(TeamModel.project_id == project_id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def remove(self, team: Team) -> bool:
        return await remove_by_pk(self._session, TeamModel.id, team.id)

    @staticmethod
    def _to_model(team: Team) -> TeamModel:
        return TeamModel(
            id=team.id,
            project_id=team.project_id,
            name=team.name,
            created_time=team.created_at,
            updated_time=team.updated_at,
            agent_slots=[
                AgentSlotModel(
                    id=slot.id,
                    team_id=slot.team_id,
                    name=slot.name,
                    role=slot.role,
                    workspace_ref=slot.workspace_ref,
                    created_time=slot.created_at,
                )
                for slot in team.agent_slots
            ],
        )

    @staticmethod
    def _to_domain(model: TeamModel) -> Team:
        return Team(
            id=model.id,
            project_id=model.project_id,
            name=model.name,
            created_at=model.created_time,
            updated_at=model.updated_time,
            agent_slots=[
                AgentSlot(
                    id=slot.id,
                    team_id=slot.team_id,
                    name=slot.name,
                    role=slot.role,
                    workspace_ref=slot.workspace_ref,
                    created_at=slot.created_time,
                )
                for slot in model.agent_slots
            ],
        )

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from domain.team.model.handoff import Handoff, HandoffArtifact
from domain.team.model.status import HandoffStatus
from domain.team.repository.handoff_repository import HandoffRepository
from infr.repository.repo_helpers import remove_by_pk
from infr.repository.team_model import CardHandoffModel, HandoffArtifactModel


class HandoffRepositoryImpl(HandoffRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, handoff: Handoff) -> None:
        await self._session.merge(self._to_model(handoff))
        await self._session.flush()

    async def find_by_id(self, handoff_id: str) -> Handoff | None:
        stmt = (
            select(CardHandoffModel)
            .options(selectinload(CardHandoffModel.artifacts))
            .where(CardHandoffModel.id == handoff_id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def find_by_card_id(self, card_id: str) -> list[Handoff]:
        stmt = (
            select(CardHandoffModel)
            .options(selectinload(CardHandoffModel.artifacts))
            .where(CardHandoffModel.card_id == card_id)
            .order_by(CardHandoffModel.created_time.asc(), CardHandoffModel.id.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(model) for model in result.scalars().all()]

    async def remove(self, handoff: Handoff) -> bool:
        return await remove_by_pk(self._session, CardHandoffModel.id, handoff.id)

    @staticmethod
    def _to_model(handoff: Handoff) -> CardHandoffModel:
        return CardHandoffModel(
            id=handoff.id,
            team_id=handoff.team_id,
            card_id=handoff.card_id,
            source_execution_id=handoff.source_execution_id,
            source_agent_slot_id=handoff.source_agent_slot_id,
            target_agent_slot_id=handoff.target_agent_slot_id,
            summary=handoff.summary,
            status=handoff.status.value,
            created_time=handoff.created_at,
            resolved_time=handoff.resolved_at,
            artifacts=[
                HandoffArtifactModel(
                    id=artifact.id,
                    handoff_id=artifact.handoff_id,
                    name=artifact.name,
                    path=artifact.path,
                    media_type=artifact.media_type,
                    created_time=artifact.created_at,
                )
                for artifact in handoff.artifacts
            ],
        )

    @staticmethod
    def _to_domain(model: CardHandoffModel) -> Handoff:
        return Handoff(
            id=model.id,
            team_id=model.team_id,
            card_id=model.card_id,
            source_execution_id=model.source_execution_id,
            source_agent_slot_id=model.source_agent_slot_id,
            target_agent_slot_id=model.target_agent_slot_id,
            summary=model.summary,
            status=HandoffStatus(model.status),
            created_at=model.created_time,
            resolved_at=model.resolved_time,
            artifacts=[
                HandoffArtifact(
                    id=artifact.id,
                    handoff_id=artifact.handoff_id,
                    name=artifact.name,
                    path=artifact.path,
                    media_type=artifact.media_type,
                    created_at=artifact.created_time,
                )
                for artifact in model.artifacts
            ],
        )

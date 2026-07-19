from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from domain.team.model.card_execution import CardExecution
from domain.team.model.status import CardExecutionStatus, WishCardStatus
from domain.team.model.wish_card import WishCard
from domain.team.repository.wish_card_repository import WishCardRepository
from infr.repository.repo_helpers import remove_by_pk
from infr.repository.team_model import CardExecutionModel, WishCardModel


class WishCardRepositoryImpl(WishCardRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, wish_card: WishCard) -> None:
        await self._session.merge(self._to_model(wish_card))
        await self._session.flush()

    async def find_by_id(self, wish_card_id: str) -> WishCard | None:
        stmt = (
            select(WishCardModel)
            .options(selectinload(WishCardModel.executions))
            .where(WishCardModel.id == wish_card_id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def find_by_team_id(self, team_id: str) -> list[WishCard]:
        stmt = (
            select(WishCardModel)
            .options(selectinload(WishCardModel.executions))
            .where(WishCardModel.team_id == team_id)
            .order_by(WishCardModel.created_time.asc(), WishCardModel.id.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(model) for model in result.scalars().all()]

    async def remove(self, wish_card: WishCard) -> bool:
        return await remove_by_pk(self._session, WishCardModel.id, wish_card.id)

    @staticmethod
    def _to_model(card: WishCard) -> WishCardModel:
        return WishCardModel(
            id=card.id,
            team_id=card.team_id,
            title=card.title,
            description=card.description,
            status=card.status.value,
            assigned_agent_slot_id=card.assigned_agent_slot_id,
            created_time=card.created_at,
            updated_time=card.updated_at,
            executions=[
                CardExecutionModel(
                    id=execution.id,
                    card_id=execution.card_id,
                    agent_slot_id=execution.agent_slot_id,
                    status=execution.status.value,
                    failure_reason=execution.failure_reason,
                    created_time=execution.created_at,
                    started_time=execution.started_at,
                    ended_time=execution.ended_at,
                    session_id=execution.session_id,
                )
                for execution in card.executions
            ],
        )

    @staticmethod
    def _to_domain(model: WishCardModel) -> WishCard:
        return WishCard(
            id=model.id,
            team_id=model.team_id,
            title=model.title,
            description=model.description,
            status=WishCardStatus(model.status),
            assigned_agent_slot_id=model.assigned_agent_slot_id,
            created_at=model.created_time,
            updated_at=model.updated_time,
            executions=[
                CardExecution(
                    id=execution.id,
                    card_id=execution.card_id,
                    agent_slot_id=execution.agent_slot_id,
                    status=CardExecutionStatus(execution.status),
                    failure_reason=execution.failure_reason,
                    created_at=execution.created_time,
                    started_at=execution.started_time,
                    ended_at=execution.ended_time,
                    session_id=execution.session_id,
                )
                for execution in model.executions
            ],
        )

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.team.model.card_execution import CardExecution
from domain.team.model.status import CardExecutionStatus
from domain.team.repository.card_execution_repository import CardExecutionRepository
from infr.repository.repo_helpers import remove_by_pk
from infr.repository.team_model import CardExecutionModel


class CardExecutionRepositoryImpl(CardExecutionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, execution: CardExecution) -> None:
        await self._session.merge(self._to_model(execution))
        await self._session.flush()

    async def find_by_id(self, execution_id: str) -> CardExecution | None:
        stmt = select(CardExecutionModel).where(CardExecutionModel.id == execution_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def find_by_card_id(self, card_id: str) -> list[CardExecution]:
        stmt = (
            select(CardExecutionModel)
            .where(CardExecutionModel.card_id == card_id)
            .order_by(CardExecutionModel.created_time.asc(), CardExecutionModel.id.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(model) for model in result.scalars().all()]

    async def remove(self, execution: CardExecution) -> bool:
        return await remove_by_pk(self._session, CardExecutionModel.id, execution.id)

    async def find_non_terminal(self) -> list[CardExecution]:
        stmt = select(CardExecutionModel).where(
            CardExecutionModel.status.notin_(["completed", "failed", "cancelled"])
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(model) for model in result.scalars().all()]

    async def remove_by_card_id(self, card_id: str) -> None:
        stmt = delete(CardExecutionModel).where(CardExecutionModel.card_id == card_id)
        await self._session.execute(stmt)
        await self._session.flush()

    @staticmethod
    def _to_model(execution: CardExecution) -> CardExecutionModel:
        return CardExecutionModel(
            id=execution.id,
            card_id=execution.card_id,
            agent_slot_id=execution.agent_slot_id,
            status=execution.status.value,
            failure_reason=execution.failure_reason,
            created_time=execution.created_at,
            started_time=execution.started_at,
            ended_time=execution.ended_at,
            session_id=execution.session_id,
            idempotency_key=execution.idempotency_key,
        )

    @staticmethod
    def _to_domain(model: CardExecutionModel) -> CardExecution:
        return CardExecution(
            id=model.id,
            card_id=model.card_id,
            agent_slot_id=model.agent_slot_id,
            status=CardExecutionStatus(model.status),
            failure_reason=model.failure_reason,
            created_at=model.created_time,
            started_at=model.started_time,
            ended_at=model.ended_time,
            session_id=model.session_id,
            idempotency_key=model.idempotency_key,
        )

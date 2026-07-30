from __future__ import annotations

from sqlalchemy import delete, select, update
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

    async def save_terminal_if_non_terminal(self, execution: CardExecution) -> bool:
        """UPDATE the execution row only when it is still non-terminal in DB.

        Returns True when exactly one row was updated (this caller won the
        race), False when rowcount == 0 (another writer already persisted a
        terminal state for this execution).
        """
        _TERMINAL = ["completed", "failed", "cancelled"]
        stmt = (
            update(CardExecutionModel)
            .where(
                CardExecutionModel.id == execution.id,
                CardExecutionModel.status.notin_(_TERMINAL),
            )
            .values(
                status=execution.status.value,
                failure_reason=execution.failure_reason,
                failure_category=(
                    execution.failure_category.value if execution.failure_category else None
                ),
                failure_phase=(
                    execution.failure_phase.value if execution.failure_phase else None
                ),
                failure_retryable=execution.failure_retryable,
                ended_time=execution.ended_at,
            )
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0

    @staticmethod
    def _to_model(execution: CardExecution) -> CardExecutionModel:
        return CardExecutionModel(
            id=execution.id,
            card_id=execution.card_id,
            agent_slot_id=execution.agent_slot_id,
            status=execution.status.value,
            failure_reason=execution.failure_reason,
            failure_category=execution.failure_category.value if execution.failure_category else None,
            failure_phase=execution.failure_phase.value if execution.failure_phase else None,
            failure_retryable=execution.failure_retryable,
            triggered_by=execution.triggered_by,
            delegated_by_slot_id=execution.delegated_by_slot_id,
            flow_plan_id=execution.flow_plan_id,
            flow_step_id=execution.flow_step_id,
            timeout_at=execution.timeout_at,
            created_time=execution.created_at,
            started_time=execution.started_at,
            ended_time=execution.ended_at,
            session_id=execution.session_id,
            idempotency_key=execution.idempotency_key,
            input_stage_output_id=execution.input_stage_output_id,
        )

    @staticmethod
    def _to_domain(model: CardExecutionModel) -> CardExecution:
        from domain.team.model.status import ExecutionFailureCategory, ExecutionFailurePhase

        return CardExecution(
            id=model.id,
            card_id=model.card_id,
            agent_slot_id=model.agent_slot_id,
            status=CardExecutionStatus(model.status),
            failure_reason=model.failure_reason,
            failure_category=ExecutionFailureCategory(model.failure_category) if model.failure_category else None,
            failure_phase=ExecutionFailurePhase(model.failure_phase) if model.failure_phase else None,
            failure_retryable=model.failure_retryable,
            triggered_by=model.triggered_by,
            delegated_by_slot_id=model.delegated_by_slot_id,
            flow_plan_id=model.flow_plan_id,
            flow_step_id=model.flow_step_id,
            timeout_at=model.timeout_at,
            created_at=model.created_time,
            started_at=model.started_time,
            ended_at=model.ended_time,
            session_id=model.session_id,
            idempotency_key=model.idempotency_key,
            input_stage_output_id=model.input_stage_output_id,
        )

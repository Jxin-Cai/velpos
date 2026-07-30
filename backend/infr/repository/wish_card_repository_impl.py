from __future__ import annotations

import json

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from domain.team.model.card_execution import CardExecution
from domain.team.model.status import (
    CardExecutionStatus,
    ExecutionFailureCategory,
    ExecutionFailurePhase,
    WishCardStatus,
)
from domain.team.model.wish_card import WishCard
from domain.team.repository.wish_card_repository import WishCardRepository
from infr.repository.team_model import CardExecutionModel, WishCardModel


class WishCardRepositoryImpl(WishCardRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, wish_card: WishCard) -> None:
        await self._session.merge(self._to_model(wish_card))
        await self._session.flush()

    async def save_state(self, wish_card: WishCard) -> None:
        """Update only the wish-card row.

        Terminal execution transitions use a conditional UPDATE of the child
        row. Saving the whole aggregate immediately afterwards can merge a
        stale execution model from the session identity map and undo that
        transition. Keeping this write scoped to the parent row preserves the
        atomic child update.
        """
        stmt = (
            update(WishCardModel)
            .where(WishCardModel.id == wish_card.id)
            .values(
                title=wish_card.title,
                description=wish_card.description,
                status=wish_card.status.value,
                version=wish_card.version,
                assigned_agent_slot_id=wish_card.assigned_agent_slot_id,
                creator_id=wish_card.creator_id,
                attribution_chain=(
                    json.dumps(wish_card.attribution_chain)
                    if wish_card.attribution_chain
                    else "[]"
                ),
                updated_time=wish_card.updated_at,
            )
        )
        result = await self._session.execute(stmt)
        if result.rowcount != 1:
            raise LookupError(f"Wish card {wish_card.id} not found")
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
        # Eager-load executions before delete. WishCardModel.executions is a
        # delete-orphan relationship, so session.delete() cascades to it; under
        # an async session an unloaded relationship would raise MissingGreenlet
        # when the cascade tries to lazy-load it. Callers that pre-delete the
        # executions still hit this path, so the eager load returns an empty
        # collection and the cascade is a no-op.
        stmt = (
            select(WishCardModel)
            .options(selectinload(WishCardModel.executions))
            .where(WishCardModel.id == wish_card.id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    @staticmethod
    def _to_model(card: WishCard) -> WishCardModel:
        return WishCardModel(
            id=card.id,
            team_id=card.team_id,
            title=card.title,
            description=card.description,
            status=card.status.value,
            version=card.version,
            assigned_agent_slot_id=card.assigned_agent_slot_id,
            creator_id=card.creator_id,
            attribution_chain=json.dumps(card.attribution_chain) if card.attribution_chain else "[]",
            created_time=card.created_at,
            updated_time=card.updated_at,
            executions=[
                CardExecutionModel(
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
            creator_id=model.creator_id,
            attribution_chain=json.loads(model.attribution_chain) if model.attribution_chain else [],
            _version=model.version,
            created_at=model.created_time,
            updated_at=model.updated_time,
            executions=[
                CardExecution(
                    id=execution.id,
                    card_id=execution.card_id,
                    agent_slot_id=execution.agent_slot_id,
                    status=CardExecutionStatus(execution.status),
                    failure_reason=execution.failure_reason,
                    failure_category=ExecutionFailureCategory(execution.failure_category) if execution.failure_category else None,
                    failure_phase=ExecutionFailurePhase(execution.failure_phase) if execution.failure_phase else None,
                    failure_retryable=execution.failure_retryable,
                    triggered_by=execution.triggered_by,
                    delegated_by_slot_id=execution.delegated_by_slot_id,
                    flow_plan_id=execution.flow_plan_id,
                    flow_step_id=execution.flow_step_id,
                    timeout_at=execution.timeout_at,
                    created_at=execution.created_time,
                    started_at=execution.started_time,
                    ended_at=execution.ended_time,
                    session_id=execution.session_id,
                    idempotency_key=execution.idempotency_key,
                    input_stage_output_id=execution.input_stage_output_id,
                )
                for execution in model.executions
            ],
        )

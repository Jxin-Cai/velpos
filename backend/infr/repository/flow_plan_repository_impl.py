from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from domain.team.model.flow_plan import FlowPlan, FlowStep
from domain.team.model.status import FlowMode, FlowPlanStatus, FlowStepStatus
from domain.team.repository.flow_plan_repository import FlowPlanRepository
from infr.repository.team_model import FlowPlanModel, FlowPlanStepModel


class FlowPlanRepositoryImpl(FlowPlanRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, flow_plan: FlowPlan) -> None:
        await self._session.merge(self._to_model(flow_plan))
        await self._session.flush()

    async def find_by_id(self, plan_id: str) -> FlowPlan | None:
        stmt = (
            select(FlowPlanModel)
            .options(selectinload(FlowPlanModel.steps))
            .where(FlowPlanModel.id == plan_id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def find_active_by_card_id(self, card_id: str) -> FlowPlan | None:
        stmt = (
            select(FlowPlanModel)
            .options(selectinload(FlowPlanModel.steps))
            .where(
                FlowPlanModel.card_id == card_id,
                FlowPlanModel.status == FlowPlanStatus.ACTIVE.value,
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def find_active_by_team_id(self, team_id: str) -> list[FlowPlan]:
        stmt = (
            select(FlowPlanModel)
            .options(selectinload(FlowPlanModel.steps))
            .where(
                FlowPlanModel.team_id == team_id,
                FlowPlanModel.status == FlowPlanStatus.ACTIVE.value,
            )
            .order_by(FlowPlanModel.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(model) for model in result.scalars().all()]

    async def find_all_active(self) -> list[FlowPlan]:
        stmt = (
            select(FlowPlanModel)
            .options(selectinload(FlowPlanModel.steps))
            .where(FlowPlanModel.status == FlowPlanStatus.ACTIVE.value)
            .order_by(FlowPlanModel.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(model) for model in result.scalars().all()]

    async def find_step_by_execution_id(self, execution_id: str) -> FlowStep | None:
        stmt = select(FlowPlanStepModel).where(
            FlowPlanStepModel.execution_id == execution_id
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._step_to_domain(model) if model is not None else None

    async def remove(self, flow_plan: FlowPlan) -> None:
        stmt = (
            select(FlowPlanModel)
            .options(selectinload(FlowPlanModel.steps))
            .where(FlowPlanModel.id == flow_plan.id)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is not None:
            await self._session.delete(model)
            await self._session.flush()

    @staticmethod
    def _to_model(plan: FlowPlan) -> FlowPlanModel:
        return FlowPlanModel(
            id=plan.id,
            team_id=plan.team_id,
            card_id=plan.card_id,
            leader_slot_id=plan.leader_slot_id,
            mode=plan.mode.value,
            status=plan.status.value,
            leader_session_id=plan.leader_session_id,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            steps=[
                FlowPlanStepModel(
                    id=step.id,
                    flow_plan_id=step.flow_plan_id,
                    sequence=step.sequence,
                    target_slot_id=step.target_slot_id,
                    status=step.status.value,
                    execution_id=step.execution_id,
                    started_at=step.started_at,
                    ended_at=step.ended_at,
                    leader_notified_at=step.leader_notified_at,
                )
                for step in plan.steps
            ],
        )

    @staticmethod
    def _to_domain(model: FlowPlanModel) -> FlowPlan:
        return FlowPlan(
            id=model.id,
            team_id=model.team_id,
            card_id=model.card_id,
            leader_slot_id=model.leader_slot_id,
            mode=FlowMode(model.mode),
            status=FlowPlanStatus(model.status),
            leader_session_id=model.leader_session_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            steps=[
                FlowStep(
                    id=step.id,
                    flow_plan_id=step.flow_plan_id,
                    sequence=step.sequence,
                    target_slot_id=step.target_slot_id,
                    status=FlowStepStatus(step.status),
                    execution_id=step.execution_id,
                    started_at=step.started_at,
                    ended_at=step.ended_at,
                    leader_notified_at=step.leader_notified_at,
                )
                for step in sorted(model.steps, key=lambda s: s.sequence)
            ],
        )

    @staticmethod
    def _step_to_domain(model: FlowPlanStepModel) -> FlowStep:
        return FlowStep(
            id=model.id,
            flow_plan_id=model.flow_plan_id,
            sequence=model.sequence,
            target_slot_id=model.target_slot_id,
            status=FlowStepStatus(model.status),
            execution_id=model.execution_id,
            started_at=model.started_at,
            ended_at=model.ended_at,
            leader_notified_at=model.leader_notified_at,
        )

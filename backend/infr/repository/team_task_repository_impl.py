from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.team_task.model.team_task import TeamTask
from domain.team_task.model.team_task_status import TeamTaskStatus
from domain.team_task.repository.team_task_repository import TeamTaskRepository
from domain.shared.utils import safe_json_loads
from infr.repository.team_task_model import TeamTaskModel
from infr.repository.repo_helpers import remove_by_pk


class TeamTaskRepositoryImpl(TeamTaskRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, task: TeamTask) -> None:
        model = self._to_model(task)
        await self._session.merge(model)
        await self._session.flush()

    async def find_by_id(self, task_id: str) -> TeamTask | None:
        stmt = select(TeamTaskModel).where(TeamTaskModel.task_id == task_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_coordinator(self, coordinator_session_id: str) -> list[TeamTask]:
        stmt = (
            select(TeamTaskModel)
            .where(TeamTaskModel.coordinator_session_id == coordinator_session_id)
            .order_by(TeamTaskModel.created_time.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_running_by_coordinator(self, coordinator_session_id: str) -> list[TeamTask]:
        stmt = (
            select(TeamTaskModel)
            .where(
                TeamTaskModel.coordinator_session_id == coordinator_session_id,
                TeamTaskModel.status.in_(["running", "waiting_for_help"]),
            )
            .order_by(TeamTaskModel.created_time.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def remove(self, task_id: str) -> bool:
        return await remove_by_pk(self._session, TeamTaskModel.task_id, task_id)

    @staticmethod
    def _to_model(task: TeamTask) -> TeamTaskModel:
        return TeamTaskModel(
            task_id=task.task_id,
            main_project_id=task.main_project_id,
            coordinator_session_id=task.coordinator_session_id,
            target_project_id=task.target_project_id,
            target_role=task.target_role,
            worker_session_id=task.worker_session_id,
            prompt=task.prompt,
            context_json=task.context,
            status=task.status.value,
            result_summary=task.result_summary,
            result_data_json=task.result_data or None,
            error_message=task.error_message,
            parent_task_id=task.parent_task_id,
            depth=task.depth,
            pipeline_step=task.pipeline_step,
            trace_id=task.trace_id,
            created_time=task.created_at,
            completed_time=task.completed_at,
            duration_ms=task.duration_ms,
            cost_usd=task.cost_usd,
        )

    @staticmethod
    def _to_domain(model: TeamTaskModel) -> TeamTask:
        result_data = model.result_data_json
        if isinstance(result_data, str):
            result_data = safe_json_loads(result_data)
        return TeamTask.reconstitute(
            task_id=model.task_id,
            main_project_id=model.main_project_id,
            coordinator_session_id=model.coordinator_session_id,
            target_project_id=model.target_project_id,
            target_role=model.target_role,
            worker_session_id=model.worker_session_id,
            prompt=model.prompt,
            context=model.context_json or "",
            status=TeamTaskStatus(model.status),
            result_summary=model.result_summary,
            result_data=result_data or {},
            error_message=model.error_message,
            parent_task_id=model.parent_task_id,
            depth=model.depth,
            pipeline_step=model.pipeline_step,
            trace_id=model.trace_id if model.trace_id else "",
            created_at=model.created_time,
            completed_at=model.completed_time,
            duration_ms=model.duration_ms,
            cost_usd=model.cost_usd,
        )

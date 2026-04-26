from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.scheduler.model.scheduled_task import ScheduledTask, ScheduledTaskRun
from domain.scheduler.repository.scheduled_task_repository import ScheduledTaskRepository
from infr.repository.scheduled_task_model import ScheduledTaskModel, ScheduledTaskRunModel


class ScheduledTaskRepositoryImpl(ScheduledTaskRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, task: ScheduledTask) -> None:
        await self._session.merge(self._to_model(task))
        await self._session.flush()

    async def save_run(self, run: ScheduledTaskRun) -> None:
        await self._session.merge(self._run_to_model(run))
        await self._session.flush()

    async def find_by_id(self, task_id: str) -> ScheduledTask | None:
        stmt = select(ScheduledTaskModel).where(ScheduledTaskModel.id == task_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def find_all(self) -> list[ScheduledTask]:
        stmt = select(ScheduledTaskModel).order_by(ScheduledTaskModel.created_time.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_due(self, now: datetime) -> list[ScheduledTask]:
        stmt = (
            select(ScheduledTaskModel)
            .where(
                ScheduledTaskModel.enabled == 1,
                ScheduledTaskModel.next_run_time.is_not(None),
                ScheduledTaskModel.next_run_time <= now,
            )
            .order_by(ScheduledTaskModel.next_run_time.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_runs_by_task_id(self, task_id: str) -> list[ScheduledTaskRun]:
        stmt = (
            select(ScheduledTaskRunModel)
            .where(ScheduledTaskRunModel.task_id == task_id)
            .order_by(ScheduledTaskRunModel.started_time.desc())
            .limit(20)
        )
        result = await self._session.execute(stmt)
        return [self._run_to_domain(m) for m in result.scalars().all()]

    async def remove(self, task_id: str) -> bool:
        stmt = select(ScheduledTaskModel).where(ScheduledTaskModel.id == task_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    async def commit(self) -> None:
        await self._session.commit()

    @staticmethod
    def _to_model(task: ScheduledTask) -> ScheduledTaskModel:
        return ScheduledTaskModel(
            id=task.id,
            project_id=task.project_id,
            session_id=task.session_id,
            channel_id=task.channel_id,
            name=task.name,
            prompt=task.prompt,
            cron_expr=task.cron_expr,
            enabled=1 if task.enabled else 0,
            auto_unbind_after_run=1 if task.auto_unbind_after_run else 0,
            delete_session_on_success=1 if task.delete_session_on_success else 0,
            next_run_time=task.next_run_time,
            created_time=task.created_time,
        )

    @staticmethod
    def _to_domain(model: ScheduledTaskModel) -> ScheduledTask:
        return ScheduledTask(
            id=model.id,
            project_id=model.project_id,
            session_id=model.session_id,
            channel_id=model.channel_id,
            name=model.name,
            prompt=model.prompt,
            cron_expr=model.cron_expr,
            enabled=model.enabled == 1,
            auto_unbind_after_run=model.auto_unbind_after_run == 1,
            delete_session_on_success=model.delete_session_on_success == 1,
            next_run_time=model.next_run_time,
            created_time=model.created_time,
        )

    @staticmethod
    def _run_to_model(run: ScheduledTaskRun) -> ScheduledTaskRunModel:
        return ScheduledTaskRunModel(
            id=run.id,
            task_id=run.task_id,
            status=run.status,
            started_time=run.started_time,
            ended_time=run.ended_time,
            result_session_id=run.result_session_id,
            error_message=run.error_message,
        )

    @staticmethod
    def _run_to_domain(model: ScheduledTaskRunModel) -> ScheduledTaskRun:
        return ScheduledTaskRun(
            id=model.id,
            task_id=model.task_id,
            status=model.status,
            started_time=model.started_time,
            ended_time=model.ended_time,
            result_session_id=model.result_session_id,
            error_message=model.error_message,
        )

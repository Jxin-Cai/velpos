from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.session.model.session_run_step import SessionRunStep
from domain.session.repository.session_run_step_repository import SessionRunStepRepository
from infr.repository.session_run_step_model import SessionRunStepModel


class SessionRunStepRepositoryImpl(SessionRunStepRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, step: SessionRunStep) -> None:
        await self._session.merge(self._to_model(step))
        await self._session.flush()

    async def find_by_run_id(self, session_id: str, run_id: str) -> list[SessionRunStep]:
        stmt = (
            select(SessionRunStepModel)
            .where(
                SessionRunStepModel.session_id == session_id,
                SessionRunStepModel.run_id == run_id,
            )
            .order_by(SessionRunStepModel.started_time.asc(), SessionRunStepModel.id.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_latest_run_id(self, session_id: str) -> str:
        stmt = (
            select(SessionRunStepModel.run_id)
            .where(SessionRunStepModel.session_id == session_id)
            .order_by(SessionRunStepModel.started_time.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() or ""

    async def commit(self) -> None:
        await self._session.commit()

    @staticmethod
    def _to_model(step: SessionRunStep) -> SessionRunStepModel:
        return SessionRunStepModel(
            id=step.id,
            session_id=step.session_id,
            run_id=step.run_id,
            step_type=step.step_type,
            status=step.status,
            title=step.title,
            payload_json=json.dumps(step.payload, ensure_ascii=False) if step.payload else "",
            started_time=step.started_time,
            ended_time=step.ended_time,
            duration_ms=step.duration_ms,
        )

    @staticmethod
    def _to_domain(model: SessionRunStepModel) -> SessionRunStep:
        payload: dict[str, Any]
        try:
            payload = json.loads(model.payload_json) if model.payload_json else {}
        except (json.JSONDecodeError, TypeError):
            payload = {}
        return SessionRunStep(
            id=model.id,
            session_id=model.session_id,
            run_id=model.run_id,
            step_type=model.step_type,
            status=model.status,
            title=model.title,
            payload=payload,
            started_time=model.started_time,
            ended_time=model.ended_time,
            duration_ms=model.duration_ms,
        )

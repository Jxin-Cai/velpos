from __future__ import annotations

import json

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.session.model.trace_span import TraceSpan
from domain.session.repository.trace_span_repository import TraceSpanRepository
from domain.shared.utils import safe_json_loads
from infr.repository.trace_span_model import TraceSpanModel


class TraceSpanRepositoryImpl(TraceSpanRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, span: TraceSpan) -> None:
        try:
            await self._session.merge(self._to_model(span))
            await self._session.flush()
        except Exception:
            await self._session.rollback()
            raise

    async def save_batch(self, spans: list[TraceSpan]) -> None:
        if not spans:
            return
        try:
            for span in spans:
                await self._session.merge(self._to_model(span))
            await self._session.flush()
        except Exception:
            await self._session.rollback()
            raise

    async def update(self, span: TraceSpan) -> None:
        await self.save(span)

    async def update_batch(self, spans: list[TraceSpan]) -> None:
        await self.save_batch(spans)

    async def find_by_id(self, span_id: str) -> TraceSpan | None:
        stmt = select(TraceSpanModel).where(TraceSpanModel.id == span_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def find_by_run(self, session_id: str, run_id: str) -> list[TraceSpan]:
        stmt = (
            select(TraceSpanModel)
            .where(
                TraceSpanModel.session_id == session_id,
                TraceSpanModel.run_id == run_id,
            )
            .order_by(TraceSpanModel.started_time.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_by_session(self, session_id: str, limit: int = 1000) -> list[TraceSpan]:
        stmt = (
            select(TraceSpanModel)
            .where(TraceSpanModel.session_id == session_id)
            .order_by(TraceSpanModel.started_time.desc())
            .limit(max(1, min(limit, 5000)))
        )
        result = await self._session.execute(stmt)
        models = list(result.scalars().all())
        models.reverse()
        return [self._to_domain(m) for m in models]

    async def find_running(self) -> list[TraceSpan]:
        stmt = (
            select(TraceSpanModel)
            .where(TraceSpanModel.status == TraceSpan.STATUS_RUNNING)
            .order_by(
                TraceSpanModel.started_time.asc(),
                TraceSpanModel.sequence.asc(),
            )
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(model) for model in result.scalars().all()]

    async def find_running_by_tool_use_id(self, session_id: str, tool_use_id: str) -> TraceSpan | None:
        stmt = (
            select(TraceSpanModel)
            .where(
                TraceSpanModel.session_id == session_id,
                TraceSpanModel.tool_use_id == tool_use_id,
                TraceSpanModel.status == TraceSpan.STATUS_RUNNING,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def find_running_by_agent_id(self, session_id: str, agent_id: str) -> TraceSpan | None:
        stmt = (
            select(TraceSpanModel)
            .where(
                TraceSpanModel.session_id == session_id,
                TraceSpanModel.agent_id == agent_id,
                TraceSpanModel.status == TraceSpan.STATUS_RUNNING,
            )
            .order_by(TraceSpanModel.started_time.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def delete_by_session(self, session_id: str) -> int:
        stmt = delete(TraceSpanModel).where(TraceSpanModel.session_id == session_id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount  # type: ignore[return-value]

    async def commit(self) -> None:
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

    @staticmethod
    def _to_model(span: TraceSpan) -> TraceSpanModel:
        return TraceSpanModel(
            id=span.id,
            session_id=span.session_id,
            run_id=span.run_id,
            parent_span_id=span.parent_span_id,
            span_type=span.span_type,
            name=span.name,
            status=span.status,
            agent_id=span.agent_id,
            tool_use_id=span.tool_use_id,
            input_preview=span.input_preview,
            output_preview=span.output_preview,
            metadata_json=json.dumps(span.metadata, ensure_ascii=False, default=str) if span.metadata else "{}",
            started_time=span.started_time,
            ended_time=span.ended_time,
            duration_ms=span.duration_ms,
            created_time=span.created_time,
            sequence=span.sequence,
            revision=span.revision,
        )

    @staticmethod
    def _to_domain(model: TraceSpanModel) -> TraceSpan:
        return TraceSpan(
            id=model.id,
            session_id=model.session_id,
            run_id=model.run_id,
            parent_span_id=model.parent_span_id,
            span_type=model.span_type,
            name=model.name,
            status=model.status,
            agent_id=model.agent_id,
            tool_use_id=model.tool_use_id,
            input_preview=model.input_preview,
            output_preview=model.output_preview,
            metadata=safe_json_loads(model.metadata_json),
            started_time=model.started_time,
            ended_time=model.ended_time,
            duration_ms=model.duration_ms,
            created_time=model.created_time,
            sequence=model.sequence,
            revision=model.revision,
        )

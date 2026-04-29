from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.session.model.session_timeline_event import SessionTimelineEvent
from domain.session.repository.session_timeline_event_repository import SessionTimelineEventRepository
from infr.repository.session_timeline_event_model import SessionTimelineEventModel


class SessionTimelineEventRepositoryImpl(SessionTimelineEventRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, event: SessionTimelineEvent) -> None:
        try:
            await self._session.merge(self._to_model(event))
            await self._session.flush()
        except Exception:
            await self._session.rollback()
            raise

    async def find_by_session_id(
        self,
        session_id: str,
        limit: int = 500,
        event_types: list[str] | None = None,
    ) -> list[SessionTimelineEvent]:
        stmt = select(SessionTimelineEventModel).where(SessionTimelineEventModel.session_id == session_id)
        if event_types:
            stmt = stmt.where(SessionTimelineEventModel.event_type.in_(event_types))
        stmt = stmt.order_by(
            SessionTimelineEventModel.created_time.desc(),
            SessionTimelineEventModel.seq.desc(),
        ).limit(max(1, min(limit, 1000)))
        result = await self._session.execute(stmt)
        models = list(result.scalars().all())
        models.reverse()
        return [self._to_domain(m) for m in models]

    async def find_by_run_id(self, session_id: str, run_id: str) -> list[SessionTimelineEvent]:
        stmt = (
            select(SessionTimelineEventModel)
            .where(
                SessionTimelineEventModel.session_id == session_id,
                SessionTimelineEventModel.run_id == run_id,
            )
            .order_by(SessionTimelineEventModel.seq.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def next_seq(self, session_id: str, run_id: str) -> int:
        stmt = select(func.max(SessionTimelineEventModel.seq)).where(
            SessionTimelineEventModel.session_id == session_id,
            SessionTimelineEventModel.run_id == (run_id or "external"),
        )
        try:
            result = await self._session.execute(stmt)
        except Exception:
            await self._session.rollback()
            raise
        current = result.scalar_one_or_none() or 0
        return int(current) + 1

    async def commit(self) -> None:
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

    async def rollback(self) -> None:
        await self._session.rollback()

    @staticmethod
    def _to_model(event: SessionTimelineEvent) -> SessionTimelineEventModel:
        return SessionTimelineEventModel(
            id=event.id,
            session_id=event.session_id,
            run_id=event.run_id,
            seq=event.seq,
            event_type=event.event_type,
            status=event.status,
            title=event.title,
            payload_json=json.dumps(event.payload, ensure_ascii=False) if event.payload else "",
            started_time=event.started_time,
            ended_time=event.ended_time,
            duration_ms=event.duration_ms,
            created_time=event.created_time,
        )

    @staticmethod
    def _to_domain(model: SessionTimelineEventModel) -> SessionTimelineEvent:
        payload: dict[str, Any]
        try:
            payload = json.loads(model.payload_json) if model.payload_json else {}
        except (json.JSONDecodeError, TypeError):
            payload = {}
        return SessionTimelineEvent(
            id=model.id,
            session_id=model.session_id,
            run_id=model.run_id,
            seq=model.seq,
            event_type=model.event_type,
            status=model.status,
            title=model.title,
            payload=payload,
            started_time=model.started_time,
            ended_time=model.ended_time,
            duration_ms=model.duration_ms,
            created_time=model.created_time,
        )

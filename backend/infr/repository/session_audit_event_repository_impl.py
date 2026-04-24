from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.session.model.session_audit_event import SessionAuditEvent
from domain.session.repository.session_audit_event_repository import SessionAuditEventRepository
from infr.repository.session_audit_event_model import SessionAuditEventModel


class SessionAuditEventRepositoryImpl(SessionAuditEventRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, event: SessionAuditEvent) -> None:
        model = SessionAuditEventModel(
            id=event.id,
            session_id=event.session_id,
            event_type=event.event_type,
            actor=event.actor,
            payload_json=json.dumps(event.payload, ensure_ascii=False) if event.payload else "",
            created_time=event.created_time,
        )
        self._session.add(model)
        await self._session.flush()

    async def find_by_session_id(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[SessionAuditEvent]:
        stmt = (
            select(SessionAuditEventModel)
            .where(SessionAuditEventModel.session_id == session_id)
            .order_by(SessionAuditEventModel.created_time.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    @staticmethod
    def _to_domain(model: SessionAuditEventModel) -> SessionAuditEvent:
        payload: dict[str, Any]
        try:
            payload = json.loads(model.payload_json) if model.payload_json else {}
        except (json.JSONDecodeError, TypeError):
            payload = {}
        return SessionAuditEvent(
            id=model.id,
            session_id=model.session_id,
            event_type=model.event_type,
            actor=model.actor,
            payload=payload,
            created_time=model.created_time,
        )

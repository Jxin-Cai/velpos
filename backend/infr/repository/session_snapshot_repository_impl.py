from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.session.model.session_snapshot import SessionSnapshot
from domain.session.repository.session_snapshot_repository import SessionSnapshotRepository
from domain.shared.utils import safe_json_loads
from infr.repository.session_branch_model import SessionSnapshotModel


class SessionSnapshotRepositoryImpl(SessionSnapshotRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, snapshot: SessionSnapshot) -> None:
        await self._session.merge(self._to_model(snapshot))
        await self._session.flush()

    async def find_by_session_id(self, session_id: str) -> list[SessionSnapshot]:
        stmt = (
            select(SessionSnapshotModel)
            .where(SessionSnapshotModel.session_id == session_id)
            .order_by(SessionSnapshotModel.message_index.desc(), SessionSnapshotModel.created_time.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    @staticmethod
    def _to_model(snapshot: SessionSnapshot) -> SessionSnapshotModel:
        return SessionSnapshotModel(
            id=snapshot.id,
            session_id=snapshot.session_id,
            message_index=snapshot.message_index,
            messages_json=json.dumps(snapshot.messages, ensure_ascii=False),
            created_time=snapshot.created_time,
        )

    @staticmethod
    def _to_domain(model: SessionSnapshotModel) -> SessionSnapshot:
        parsed = safe_json_loads(model.messages_json, default=[])
        messages = parsed if isinstance(parsed, list) else []
        return SessionSnapshot(
            id=model.id,
            session_id=model.session_id,
            message_index=model.message_index,
            messages=messages,
            created_time=model.created_time,
        )

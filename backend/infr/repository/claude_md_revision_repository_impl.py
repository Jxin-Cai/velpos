from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.memory.model.claude_md_revision import ClaudeMdRevision
from domain.memory.model.claude_md_revision_event import ClaudeMdRevisionEvent
from domain.memory.model.claude_md_revision_state import ClaudeMdRevisionState
from domain.memory.repository.claude_md_revision_repository import ClaudeMdRevisionRepository
from infr.repository.claude_md_revision_model import ClaudeMdRevisionEventModel, ClaudeMdRevisionModel


class ClaudeMdRevisionRepositoryImpl(ClaudeMdRevisionRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, revision: ClaudeMdRevision) -> None:
        await self._session.merge(self._to_model(revision))
        await self._session.flush()

    async def save_event(self, event: ClaudeMdRevisionEvent) -> None:
        self._session.add(
            ClaudeMdRevisionEventModel(
                id=event.id,
                revision_id=event.revision_id,
                from_state=event.from_state,
                to_state=event.to_state,
                payload_json=json.dumps(event.payload, ensure_ascii=False),
                created_time=event.created_time,
            )
        )
        await self._session.flush()

    async def find_by_id(self, revision_id: str) -> ClaudeMdRevision | None:
        stmt = select(ClaudeMdRevisionModel).where(ClaudeMdRevisionModel.id == revision_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def find_by_project_id(self, project_id: str) -> list[ClaudeMdRevision]:
        stmt = (
            select(ClaudeMdRevisionModel)
            .where(ClaudeMdRevisionModel.project_id == project_id)
            .order_by(ClaudeMdRevisionModel.version_no.desc(), ClaudeMdRevisionModel.created_time.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_active_by_project_id(self, project_id: str) -> ClaudeMdRevision | None:
        stmt = (
            select(ClaudeMdRevisionModel)
            .where(
                ClaudeMdRevisionModel.project_id == project_id,
                ClaudeMdRevisionModel.state == ClaudeMdRevisionState.APPLIED.value,
            )
            .order_by(ClaudeMdRevisionModel.version_no.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def next_version_no(self, project_id: str) -> int:
        stmt = select(func.max(ClaudeMdRevisionModel.version_no)).where(
            ClaudeMdRevisionModel.project_id == project_id,
        )
        result = await self._session.execute(stmt)
        current = result.scalar_one_or_none() or 0
        return int(current) + 1

    async def has_children(self, revision_id: str) -> bool:
        stmt = select(ClaudeMdRevisionModel.id).where(
            ClaudeMdRevisionModel.base_revision_id == revision_id,
        ).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def remove(self, revision_id: str) -> bool:
        revision = await self.find_by_id(revision_id)
        if revision is None:
            return False
        await self._session.execute(delete(ClaudeMdRevisionEventModel).where(
            ClaudeMdRevisionEventModel.revision_id == revision_id,
        ))
        await self._session.execute(delete(ClaudeMdRevisionModel).where(
            ClaudeMdRevisionModel.id == revision_id,
        ))
        await self._session.flush()
        return True

    @staticmethod
    def _to_model(revision: ClaudeMdRevision) -> ClaudeMdRevisionModel:
        return ClaudeMdRevisionModel(
            id=revision.id,
            project_id=revision.project_id,
            version_no=revision.version_no,
            state=revision.state.value,
            content=revision.content,
            content_hash=revision.content_hash,
            base_revision_id=revision.base_revision_id,
            base_file_hash=revision.base_file_hash,
            created_by=revision.created_by,
            created_time=revision.created_time,
            proposed_time=revision.proposed_time,
            approved_time=revision.approved_time,
            applied_time=revision.applied_time,
            rejected_time=revision.rejected_time,
            reject_reason=revision.reject_reason,
        )

    @staticmethod
    def _to_domain(model: ClaudeMdRevisionModel) -> ClaudeMdRevision:
        return ClaudeMdRevision.reconstitute(
            id=model.id,
            project_id=model.project_id,
            version_no=model.version_no,
            state=ClaudeMdRevisionState(model.state),
            content=model.content,
            content_hash=model.content_hash,
            base_revision_id=model.base_revision_id,
            base_file_hash=model.base_file_hash,
            created_by=model.created_by,
            created_time=model.created_time,
            proposed_time=model.proposed_time,
            approved_time=model.approved_time,
            applied_time=model.applied_time,
            rejected_time=model.rejected_time,
            reject_reason=model.reject_reason,
        )

    @staticmethod
    def _load_payload(payload_json: str) -> dict[str, Any]:
        try:
            return json.loads(payload_json) if payload_json else {}
        except (json.JSONDecodeError, TypeError):
            return {}

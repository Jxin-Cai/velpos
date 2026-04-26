from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.session.model.session_branch import SessionBranch
from domain.session.repository.session_branch_repository import SessionBranchRepository
from infr.repository.session_branch_model import SessionBranchModel


class SessionBranchRepositoryImpl(SessionBranchRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, branch: SessionBranch) -> None:
        await self._session.merge(self._to_model(branch))
        await self._session.flush()

    async def find_by_source_session_id(self, session_id: str) -> list[SessionBranch]:
        stmt = (
            select(SessionBranchModel)
            .where(SessionBranchModel.source_session_id == session_id)
            .order_by(SessionBranchModel.created_time.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_by_branch_session_id(self, session_id: str) -> SessionBranch | None:
        stmt = select(SessionBranchModel).where(SessionBranchModel.branch_session_id == session_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def find_by_root_session_id(self, session_id: str) -> list[SessionBranch]:
        stmt = (
            select(SessionBranchModel)
            .where(SessionBranchModel.root_session_id == session_id)
            .order_by(SessionBranchModel.created_time.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_by_group_id(self, group_id: str) -> list[SessionBranch]:
        stmt = (
            select(SessionBranchModel)
            .where(SessionBranchModel.group_id == group_id)
            .order_by(SessionBranchModel.sequence_no.asc(), SessionBranchModel.created_time.asc())
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def remove_by_branch_session_id(self, session_id: str) -> bool:
        stmt = delete(SessionBranchModel).where(SessionBranchModel.branch_session_id == session_id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return bool(result.rowcount)

    async def remove_by_group_id(self, group_id: str) -> int:
        stmt = delete(SessionBranchModel).where(SessionBranchModel.group_id == group_id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return int(result.rowcount or 0)

    @staticmethod
    def _to_model(branch: SessionBranch) -> SessionBranchModel:
        return SessionBranchModel(
            id=branch.id,
            source_session_id=branch.source_session_id,
            branch_session_id=branch.branch_session_id,
            source_message_index=branch.source_message_index,
            name=branch.name,
            root_session_id=branch.root_session_id,
            group_id=branch.group_id,
            sequence_no=branch.sequence_no,
            worktree_enabled=branch.worktree_enabled,
            worktree_path=branch.worktree_path,
            base_branch=branch.base_branch,
            created_time=branch.created_time,
        )

    @staticmethod
    def _to_domain(model: SessionBranchModel) -> SessionBranch:
        return SessionBranch(
            id=model.id,
            source_session_id=model.source_session_id,
            branch_session_id=model.branch_session_id,
            source_message_index=model.source_message_index,
            name=model.name,
            root_session_id=model.root_session_id,
            group_id=model.group_id,
            sequence_no=model.sequence_no,
            worktree_enabled=bool(model.worktree_enabled),
            worktree_path=model.worktree_path,
            base_branch=model.base_branch,
            created_time=model.created_time,
        )

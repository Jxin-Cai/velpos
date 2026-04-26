from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.evolution.model.evolution_proposal import EvolutionProposal
from domain.evolution.repository.evolution_proposal_repository import EvolutionProposalRepository
from infr.repository.evolution_proposal_model import EvolutionProposalModel


class EvolutionProposalRepositoryImpl(EvolutionProposalRepository):

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, proposal: EvolutionProposal) -> None:
        await self._session.merge(self._to_model(proposal))
        await self._session.flush()

    async def find_by_id(self, proposal_id: str) -> EvolutionProposal | None:
        result = await self._session.execute(
            select(EvolutionProposalModel).where(EvolutionProposalModel.id == proposal_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def find_by_project_id(self, project_id: str) -> list[EvolutionProposal]:
        result = await self._session.execute(
            select(EvolutionProposalModel)
            .where(EvolutionProposalModel.project_id == project_id)
            .order_by(EvolutionProposalModel.updated_time.desc())
        )
        return [self._to_domain(model) for model in result.scalars().all()]

    @staticmethod
    def _to_model(proposal: EvolutionProposal) -> EvolutionProposalModel:
        return EvolutionProposalModel(
            id=proposal.id,
            project_id=proposal.project_id,
            source_session_id=proposal.source_session_id,
            state=proposal.state,
            extracted_lessons_json=json.dumps(proposal.extracted_lessons, ensure_ascii=False),
            proposed_claude_md_revision_id=proposal.proposed_claude_md_revision_id,
            created_time=proposal.created_time,
            updated_time=proposal.updated_time,
        )

    @staticmethod
    def _to_domain(model: EvolutionProposalModel) -> EvolutionProposal:
        return EvolutionProposal(
            id=model.id,
            project_id=model.project_id,
            source_session_id=model.source_session_id,
            state=model.state,
            extracted_lessons=json.loads(model.extracted_lessons_json or "[]"),
            proposed_claude_md_revision_id=model.proposed_claude_md_revision_id,
            created_time=model.created_time,
            updated_time=model.updated_time,
        )

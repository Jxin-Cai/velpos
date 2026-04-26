from __future__ import annotations

from abc import ABC, abstractmethod

from domain.evolution.model.evolution_proposal import EvolutionProposal


class EvolutionProposalRepository(ABC):

    @abstractmethod
    async def save(self, proposal: EvolutionProposal) -> None:
        raise NotImplementedError

    @abstractmethod
    async def find_by_id(self, proposal_id: str) -> EvolutionProposal | None:
        raise NotImplementedError

    @abstractmethod
    async def find_by_project_id(self, project_id: str) -> list[EvolutionProposal]:
        raise NotImplementedError

from abc import ABC, abstractmethod

from domain.team.model.handoff import Handoff


class HandoffRepository(ABC):
    @abstractmethod
    def save(self, handoff: Handoff) -> None:
        pass

    @abstractmethod
    def find_by_id(self, handoff_id: str) -> Handoff | None:
        pass

    @abstractmethod
    def find_by_card_id(self, card_id: str) -> list[Handoff]:
        pass

    @abstractmethod
    def remove(self, handoff: Handoff) -> None:
        pass

    @abstractmethod
    def remove_by_card_id(self, card_id: str) -> None:
        """Delete every handoff (and its artifacts) belonging to the card."""
        pass

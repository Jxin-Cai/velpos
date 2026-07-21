from abc import ABC, abstractmethod

from domain.team.model.card_execution import CardExecution


class CardExecutionRepository(ABC):
    @abstractmethod
    def save(self, execution: CardExecution) -> None:
        pass

    @abstractmethod
    def find_by_id(self, execution_id: str) -> CardExecution | None:
        pass

    @abstractmethod
    def find_by_card_id(self, card_id: str) -> list[CardExecution]:
        pass

    @abstractmethod
    def remove(self, execution: CardExecution) -> None:
        pass

    @abstractmethod
    def find_non_terminal(self) -> list[CardExecution]:
        pass

    @abstractmethod
    def remove_by_card_id(self, card_id: str) -> None:
        """Delete every execution belonging to the given card."""
        pass

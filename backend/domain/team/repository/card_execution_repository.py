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

    @abstractmethod
    def save_terminal_if_non_terminal(self, execution: CardExecution) -> bool:
        """Atomically persist a terminal-state execution only when the DB row is
        still non-terminal (an optimistic-lock write).

        Returns True when the UPDATE succeeds (we won the race), False when the
        execution was already in a terminal state in the database (we lost).
        Business rules for *which* terminal state to write must be applied by
        the caller before invoking this method.
        """
        pass

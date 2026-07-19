from abc import ABC, abstractmethod

from domain.team.model.wish_card import WishCard


class WishCardRepository(ABC):
    @abstractmethod
    def save(self, wish_card: WishCard) -> None:
        pass

    @abstractmethod
    def find_by_id(self, wish_card_id: str) -> WishCard | None:
        pass

    @abstractmethod
    def find_by_team_id(self, team_id: str) -> list[WishCard]:
        pass

    @abstractmethod
    def remove(self, wish_card: WishCard) -> None:
        pass

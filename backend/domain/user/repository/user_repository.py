from __future__ import annotations

from abc import ABC, abstractmethod

from domain.user.model.user import User


class UserRepository(ABC):

    @abstractmethod
    async def save(self, user: User) -> User:
        """Save the User (insert or update). Returns the User with assigned id."""
        ...

    @abstractmethod
    async def find_by_id(self, user_id: int) -> User | None:
        ...

    @abstractmethod
    async def find_by_username(self, username: str) -> User | None:
        ...

    @abstractmethod
    async def find_all(self) -> list[User]:
        ...

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.session.model.session import Session


class SessionRepository(ABC):

    @abstractmethod
    def save(self, session: Session) -> None:
        """Save the Session aggregate root.

        If a record with the given session_id does not exist, inserts a new one (INSERT).
        If it already exists, updates all fields (UPDATE).
        Must synchronously persist the messages list and usage value object
        within a single transaction to guarantee aggregate consistency.
        """
        ...

    @abstractmethod
    def find_by_id(self, session_id: str) -> Session | None:
        """Find a Session aggregate root by session_id.

        Must load the messages list and usage value object simultaneously,
        returning a fully reconstituted aggregate via Session.reconstitute.
        Returns None if the session_id does not exist.
        """
        ...

    @abstractmethod
    def find_all(self) -> list[Session]:
        """Find all Session aggregate roots.

        Each Session must be loaded with its complete messages and usage.
        The list is ordered by creation time in descending order.
        Returns an empty list if no data exists.
        """
        ...

    @abstractmethod
    def remove(self, session_id: str) -> bool:
        """Remove the specified Session aggregate root.

        Must cascade-remove associated message records.
        Returns True if the session_id existed and was successfully removed.
        Returns False if the session_id did not exist.
        """
        ...

    @abstractmethod
    def find_by_sdk_session_id(self, sdk_session_id: str) -> Session | None:
        """Find a Session by its sdk_session_id (Claude Code session UUID).

        Returns None if no session with this sdk_session_id exists.
        """
        ...

    @abstractmethod
    async def commit(self) -> None:
        """Commit the current unit of work."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the underlying database session."""
        ...

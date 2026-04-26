from __future__ import annotations

from abc import ABC, abstractmethod

from domain.memory.model.claude_md_revision import ClaudeMdRevision
from domain.memory.model.claude_md_revision_event import ClaudeMdRevisionEvent


class ClaudeMdRevisionRepository(ABC):

    @abstractmethod
    async def save(self, revision: ClaudeMdRevision) -> None:
        """Save a CLAUDE.md revision aggregate."""
        ...

    @abstractmethod
    async def save_event(self, event: ClaudeMdRevisionEvent) -> None:
        """Append a revision state-change event."""
        ...

    @abstractmethod
    async def find_by_id(self, revision_id: str) -> ClaudeMdRevision | None:
        """Find a revision by id."""
        ...

    @abstractmethod
    async def find_by_project_id(self, project_id: str) -> list[ClaudeMdRevision]:
        """List all revisions for a project ordered by version descending."""
        ...

    @abstractmethod
    async def find_active_by_project_id(self, project_id: str) -> ClaudeMdRevision | None:
        """Find the latest applied revision for a project."""
        ...

    @abstractmethod
    async def next_version_no(self, project_id: str) -> int:
        """Return the next version number for a project."""
        ...

    @abstractmethod
    async def has_children(self, revision_id: str) -> bool:
        """Return whether another revision uses this revision as base."""
        ...

    @abstractmethod
    async def remove(self, revision_id: str) -> bool:
        """Remove a revision and its events."""
        ...

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.project.model.project import Project


class ProjectRepository(ABC):

    @abstractmethod
    def save(self, project: Project) -> None:
        """Save the Project aggregate root (insert or update)."""
        ...

    @abstractmethod
    def find_by_id(self, project_id: str) -> Project | None:
        """Find a Project by id. Returns None if not found."""
        ...

    @abstractmethod
    def find_all(self) -> list[Project]:
        """Find all Projects, ordered by sort_order desc then created_at desc."""
        ...

    @abstractmethod
    def find_by_dir_path(self, dir_path: str) -> Project | None:
        """Find a Project by dir_path. Returns None if not found."""
        ...

    @abstractmethod
    def remove(self, project_id: str) -> bool:
        """Remove a Project by id. Returns True if removed, False if not found."""
        ...

from abc import ABC, abstractmethod

from domain.team.model.team import Team


class TeamRepository(ABC):
    @abstractmethod
    def save(self, team: Team) -> None:
        pass

    @abstractmethod
    def find_by_id(self, team_id: str) -> Team | None:
        pass

    @abstractmethod
    def find_by_project_id(self, project_id: str) -> Team | None:
        pass

    @abstractmethod
    def remove(self, team: Team) -> None:
        pass

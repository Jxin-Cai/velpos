from abc import ABC, abstractmethod


class WorkspaceUnavailableError(Exception):
    """Raised when a persisted agent workspace can no longer be used."""


class WorkspaceGateway(ABC):
    @abstractmethod
    def create_independent_workspace(
        self,
        team_root: str,
        team_slug: str,
        slot_slug: str,
        project_root: str,
        agent_profile_ref: str | None = None,
    ) -> str:
        pass

    @abstractmethod
    def create_execution_workspace(
        self,
        workspace_ref: str,
        execution_id: str,
    ) -> str:
        pass

    @abstractmethod
    def remove_workspace(self, workspace_ref: str) -> None:
        pass

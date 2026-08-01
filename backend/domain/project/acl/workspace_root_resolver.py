from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class WorkspaceRootResolver(ABC):

    @abstractmethod
    def agent_root(self, user_id: int) -> Path:
        ...

    @abstractmethod
    def team_root(self, user_id: int) -> Path:
        ...

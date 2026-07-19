from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionArtifact:
    path: str
    description: str
    artifact_type: str


@dataclass(frozen=True)
class SessionContext:
    summary: str
    source_session_id: str
    sdk_session_id: str
    artifacts: tuple[SessionArtifact, ...] = ()


class SessionContextCollector(ABC):
    @abstractmethod
    async def collect(self, session_id: str) -> SessionContext:
        """Collect persisted, read-only context for a session."""

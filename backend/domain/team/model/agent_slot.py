from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from domain.team.model.team_domain_error import TeamDomainError


@dataclass(frozen=True)
class AgentSlot:
    id: str
    team_id: str
    name: str
    role: str
    workspace_ref: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        team_id: str,
        name: str,
        role: str,
        workspace_ref: str,
    ) -> "AgentSlot":
        if not team_id.strip():
            raise TeamDomainError("team_id must not be blank")
        if not name.strip():
            raise TeamDomainError("agent slot name must not be blank")
        if not role.strip():
            raise TeamDomainError("agent slot role must not be blank")
        if not workspace_ref.strip():
            raise TeamDomainError("agent slot workspace_ref must not be blank")

        return cls(
            id=str(uuid4()),
            team_id=team_id,
            name=name,
            role=role,
            workspace_ref=workspace_ref,
            created_at=datetime.now(timezone.utc),
        )
